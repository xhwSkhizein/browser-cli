from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import browser_test_support
from tests import browser_runtime

from browser_cli.errors import BrowserUnavailableError


def test_integration_collection_does_not_start_browser_processes(monkeypatch):
    import playwright.async_api

    launches = []

    async def close():
        pass

    async def launch(**kwargs):
        launches.append(kwargs)
        return SimpleNamespace(close=close)

    async def start():
        return SimpleNamespace(
            chromium=SimpleNamespace(launch=launch, launch_persistent_context=launch),
            stop=close,
        )

    monkeypatch.setattr(
        playwright.async_api, "async_playwright", lambda: SimpleNamespace(start=start)
    )
    monkeypatch.setattr(
        "browser_cli.browser.launch_preflight.ensure_browser_launch_allowed", lambda: None
    )
    monkeypatch.setattr(
        "browser_cli.profiles.discovery.discover_chrome_executable", lambda: Path("/test/chrome")
    )
    integration = Path(__file__).resolve().parents[1] / "integration"
    for name in ("test_daemon_actions", "test_task_runtime_read", "test_runtime_stability"):
        spec = importlib.util.spec_from_file_location(
            f"dock_collection_{name}", integration / f"{name}.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    assert launches == [], "Collecting tests launched Chrome and can create Dock recent-app entries"


def test_macos_test_runtime_selects_the_pinned_shell_not_desktop_chrome(monkeypatch, tmp_path):
    shell = tmp_path / "chromium_headless_shell-1234" / "chrome-headless-shell"
    shell.parent.mkdir()
    shell.write_text("")
    shell.chmod(0o755)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=f"Chrome Headless Shell test\n  Install location: {shell.parent}\n",
            stderr="",
        )

    monkeypatch.setattr(browser_test_support.subprocess, "run", run)
    monkeypatch.setattr(
        browser_test_support,
        "discover_chrome_executable",
        lambda **kwargs: pytest.fail("Desktop Chrome must not be used for macOS browser tests"),
    )
    interpreter = tmp_path / "wheel-venv/bin/python"
    env = {"PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "wheel-cache")}
    actual = browser_test_support.resolve_browser_test_executable(
        platform="darwin", python=interpreter, env=env
    )
    assert actual == shell
    assert calls[0][0][0] == str(interpreter)
    assert "--dry-run" in calls[0][0]
    assert calls[0][1]["env"] == env


@pytest.mark.parametrize("failure", ["missing", "desktop-app", "not-executable", "registry-error"])
def test_macos_test_runtime_fails_without_a_usable_shell(monkeypatch, tmp_path, failure):
    candidate = tmp_path / "chrome-headless-shell"
    if failure == "desktop-app":
        candidate = tmp_path / "Chrome.app/Contents/MacOS/chrome-headless-shell"
    if failure != "missing":
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text("")
        candidate.chmod(0o644 if failure == "not-executable" else 0o755)
    monkeypatch.setattr(
        browser_test_support.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1 if failure == "registry-error" else 0,
            stdout=f"Chrome Headless Shell test\n  Install location: {candidate.parent}\n",
            stderr="",
        ),
    )
    monkeypatch.setattr(
        browser_test_support,
        "discover_chrome_executable",
        lambda **kwargs: pytest.fail("No implicit fallback to desktop Chrome"),
    )
    with pytest.raises(RuntimeError, match="install --only-shell chromium"):
        browser_test_support.resolve_browser_test_executable(platform="darwin")


def test_linux_tests_keep_stable_chrome_coverage(monkeypatch, tmp_path):
    stable = tmp_path / "google-chrome"
    monkeypatch.setattr(browser_test_support, "discover_chrome_executable", lambda **kwargs: stable)
    assert browser_test_support.resolve_browser_test_executable(platform="linux") == stable


@pytest.mark.parametrize(
    "heading", ["Chrome Headless Shell 145", "browser: chromium-headless-shell"]
)
def test_shell_metadata_ignores_other_browser_and_ffmpeg_install_locations(heading):
    output = (
        "Chromium 145\n  Install location: /cache/chromium-1234\n\n"
        f"\x1b[1m{heading}\x1b[0m\n  Install location: /cache/shell-1234\n\n"
        "FFmpeg\n  Install location: /cache/ffmpeg-1011\n"
    )
    assert browser_test_support._headless_shell_locations(output) == [Path("/cache/shell-1234")]


def test_daemon_test_browser_configuration_survives_cold_starts_and_reload(monkeypatch, tmp_path):
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "runtime"))
    monkeypatch.setattr(browser_runtime, "get_test_browser_executable", lambda: tmp_path / "shell")
    calls = []
    monkeypatch.setattr(browser_runtime, "send_command", lambda *args: calls.append(args))
    browser_runtime.prepare_daemon_browser()
    browser_runtime.prepare_daemon_browser()
    assert len(calls) == 2
    action, args = calls[0]
    assert action == "runtime-status"
    assert args["chrome_environment"]["executable_path"] == str(tmp_path / "shell")
    assert args["chrome_environment"]["user_data_dir"] == str(tmp_path / "runtime/default-profile")
    assert calls[1] == calls[0]


def test_test_runtime_cannot_configure_the_users_default_daemon(monkeypatch):
    monkeypatch.delenv("BROWSER_CLI_HOME", raising=False)
    monkeypatch.setattr(
        browser_runtime, "send_command", lambda *args: pytest.fail("Touched the user's daemon")
    )
    with pytest.raises(RuntimeError, match="isolated BROWSER_CLI_HOME"):
        browser_runtime.prepare_daemon_browser()


def test_integration_preflight_fails_before_browser_setup_when_host_access_is_denied(monkeypatch):
    from tests.integration import conftest

    def denied():
        raise BrowserUnavailableError("LaunchServices access denied")

    monkeypatch.setattr(conftest, "ensure_browser_launch_allowed", denied)
    monkeypatch.setattr(
        conftest, "get_test_browser_executable", lambda: pytest.fail("Skipped the host preflight")
    )
    with pytest.raises(BrowserUnavailableError, match="LaunchServices access denied"):
        conftest._require_browser_runtime.__wrapped__(object())
