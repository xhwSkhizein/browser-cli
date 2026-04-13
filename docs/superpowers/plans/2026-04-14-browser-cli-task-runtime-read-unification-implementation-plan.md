# Browser CLI Task Runtime Read Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify Browser CLI one-shot `read` behind `browser_cli.task_runtime` so `BrowserCliTaskClient.read()`, `Flow.read()`, and CLI `browser-cli read` all use the same Python-side implementation and the legacy `browser_cli.runtime` package can be removed.

**Architecture:** Add a shared `task_runtime.read` module that owns one-shot read request building, cold-daemon Chrome-environment discovery, and `ReadResult` mapping. Keep `BrowserCliTaskClient` as the single public Python entrypoint, make `Flow.read()` and `commands/read.py` thin wrappers around it, then remove `src/browser_cli/runtime/` and update integration tests, docs, and `AGENTS.md` so future work follows the unified path.

**Tech Stack:** Python 3.10, pytest, Playwright-backed integration tests, Browser CLI daemon client, Markdown docs

---

## File Structure

- Create: `src/browser_cli/task_runtime/read.py`
  - Own the shared one-shot read contract: `ReadRequest`, `ReadResult`, Chrome-environment serialization, and the shared async `run_read_request(...)` orchestration.
- Modify: `src/browser_cli/task_runtime/client.py`
  - Add `BrowserCliTaskClient.__init__(chrome_environment=...)` and `read(...)`, while keeping existing daemon action helpers intact.
- Modify: `src/browser_cli/task_runtime/flow.py`
  - Add `Flow.read(...)` as a thin wrapper over `BrowserCliTaskClient.read(...)`.
- Modify: `src/browser_cli/task_runtime/__init__.py`
  - Export `ReadResult` from the public task runtime surface.
- Modify: `src/browser_cli/commands/read.py`
  - Remove direct `ReadRunner` usage and delegate CLI `read` to `BrowserCliTaskClient.read(...)`.
- Delete: `src/browser_cli/runtime/read_runner.py`
  - Remove the legacy one-shot read implementation after callers have moved.
- Delete: `src/browser_cli/runtime/__init__.py`
  - Remove the legacy runtime package shim once nothing imports it.
- Create: `tests/unit/test_task_runtime_client_read.py`
  - Lock the shared task runtime read contract, cold-daemon environment injection, empty-body failure behavior, and `Flow.read(...)` delegation.
- Modify: `tests/unit/test_cli.py`
  - Update CLI tests to patch `BrowserCliTaskClient.read(...)` instead of `ReadRunner.run(...)`.
- Delete: `tests/integration/test_read_runner.py`
  - Retire the integration test file that is named after the legacy implementation.
- Create: `tests/integration/test_task_runtime_read.py`
  - Reuse the fixture-backed coverage against `BrowserCliTaskClient.read(...)`.
- Modify: `AGENTS.md`
  - Replace stale `runtime/read_runner` navigation and ownership guidance with `task_runtime` read guidance.
- Modify: `docs/examples/task-and-automation.md`
  - Add a one-shot `Flow.read(...)` example and keep runtime guidance aligned with the unified package.

Do not update historical spec and plan documents for this cleanup. They are historical records, not durable navigation surfaces.

### Task 1: Add Shared Task Runtime Read Support

**Files:**
- Create: `src/browser_cli/task_runtime/read.py`
- Modify: `src/browser_cli/task_runtime/client.py`
- Modify: `src/browser_cli/task_runtime/flow.py`
- Modify: `src/browser_cli/task_runtime/__init__.py`
- Create: `tests/unit/test_task_runtime_client_read.py`

- [ ] **Step 1: Write the failing task runtime read unit tests**

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from browser_cli.errors import EmptyContentError
from browser_cli.profiles.discovery import ChromeEnvironment
from browser_cli.task_runtime.client import BrowserCliTaskClient
from browser_cli.task_runtime.flow import Flow
from browser_cli.task_runtime.models import FlowContext
from browser_cli.task_runtime.read import ReadResult


def _chrome_environment(tmp_path: Path) -> ChromeEnvironment:
    user_data_dir = tmp_path / "user-data"
    (user_data_dir / "Default").mkdir(parents=True)
    return ChromeEnvironment(
        executable_path=None,
        user_data_dir=user_data_dir,
        profile_directory="Default",
        source="fallback",
        fallback_reason="Chrome profile appears to be in use.",
    )


def test_client_read_injects_chrome_environment_when_daemon_is_cold(tmp_path: Path) -> None:
    chrome_environment = _chrome_environment(tmp_path)
    captured: dict[str, object] = {}

    def _fake_send_command(action: str, args=None, start_if_needed: bool = True):
        captured["action"] = action
        captured["args"] = args
        captured["start_if_needed"] = start_if_needed
        return {
            "ok": True,
            "data": {
                "body": "<html>ready</html>",
                "used_fallback_profile": True,
                "fallback_profile_dir": str(chrome_environment.user_data_dir),
                "fallback_reason": chrome_environment.fallback_reason,
            },
        }

    with patch("browser_cli.task_runtime.read.probe_socket", return_value=False), patch(
        "browser_cli.task_runtime.read.discover_chrome_environment",
        return_value=chrome_environment,
    ), patch("browser_cli.task_runtime.read.send_command", side_effect=_fake_send_command):
        result = BrowserCliTaskClient().read("https://example.com", scroll_bottom=True)

    assert captured["action"] == "read-page"
    assert captured["start_if_needed"] is True
    assert captured["args"] == {
        "url": "https://example.com",
        "output_mode": "html",
        "scroll_bottom": True,
        "chrome_environment": {
            "executable_path": None,
            "user_data_dir": str(chrome_environment.user_data_dir),
            "profile_directory": "Default",
            "profile_name": None,
            "source": "fallback",
            "fallback_reason": "Chrome profile appears to be in use.",
        },
    }
    assert result == ReadResult(
        body="<html>ready</html>",
        used_fallback_profile=True,
        fallback_profile_dir=str(chrome_environment.user_data_dir),
        fallback_reason="Chrome profile appears to be in use.",
    )


def test_client_read_raises_empty_content_error() -> None:
    with patch("browser_cli.task_runtime.read.probe_socket", return_value=True), patch(
        "browser_cli.task_runtime.read.send_command",
        return_value={"ok": True, "data": {"body": "   "}},
    ):
        with pytest.raises(EmptyContentError):
            BrowserCliTaskClient().read("https://example.com")


def test_flow_read_delegates_to_client(tmp_path: Path) -> None:
    class _FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, bool]] = []

        def read(
            self,
            url: str,
            *,
            output_mode: str = "html",
            scroll_bottom: bool = False,
        ) -> ReadResult:
            self.calls.append((url, output_mode, scroll_bottom))
            return ReadResult(body="snapshot tree")

    client = _FakeClient()
    flow = Flow(
        client=client,
        context=FlowContext(
            task_path=tmp_path / "task.py",
            task_dir=tmp_path,
            artifacts_dir=tmp_path / "artifacts",
        ),
    )

    result = flow.read("https://example.com", output_mode="snapshot", scroll_bottom=True)

    assert client.calls == [("https://example.com", "snapshot", True)]
    assert result.body == "snapshot tree"
```

- [ ] **Step 2: Run the read unit tests to verify they fail**

Run: `pytest tests/unit/test_task_runtime_client_read.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'browser_cli.task_runtime.read'` or `AttributeError: 'BrowserCliTaskClient' object has no attribute 'read'`.

- [ ] **Step 3: Add the shared task runtime read implementation**

```python
"""Shared one-shot read orchestration for the task runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from browser_cli.daemon.client import send_command
from browser_cli.daemon.transport import probe_socket
from browser_cli.errors import EmptyContentError
from browser_cli.profiles.discovery import ChromeEnvironment, discover_chrome_environment


@dataclass(slots=True)
class ReadRequest:
    url: str
    output_mode: str
    scroll_bottom: bool = False


@dataclass(slots=True)
class ReadResult:
    body: str
    used_fallback_profile: bool = False
    fallback_profile_dir: str | None = None
    fallback_reason: str | None = None


def _serialize_chrome_environment(
    chrome_environment: ChromeEnvironment,
) -> dict[str, str | None]:
    return {
        "executable_path": (
            str(chrome_environment.executable_path)
            if chrome_environment.executable_path is not None
            else None
        ),
        "user_data_dir": str(chrome_environment.user_data_dir),
        "profile_directory": chrome_environment.profile_directory,
        "profile_name": chrome_environment.profile_name,
        "source": chrome_environment.source,
        "fallback_reason": chrome_environment.fallback_reason,
    }


async def run_read_request(
    request: ReadRequest,
    *,
    chrome_environment: ChromeEnvironment | None = None,
) -> ReadResult:
    command_args = {
        "url": request.url,
        "output_mode": request.output_mode,
        "scroll_bottom": request.scroll_bottom,
    }
    if not probe_socket():
        resolved_environment = chrome_environment or discover_chrome_environment()
        command_args["chrome_environment"] = _serialize_chrome_environment(resolved_environment)
    payload = await asyncio.to_thread(send_command, "read-page", command_args)
    body = str(payload.get("data", {}).get("body") or "")
    if not body.strip():
        raise EmptyContentError()
    used_fallback = bool(payload.get("data", {}).get("used_fallback_profile"))
    return ReadResult(
        body=body,
        used_fallback_profile=used_fallback,
        fallback_profile_dir=(
            str(payload.get("data", {}).get("fallback_profile_dir"))
            if used_fallback and payload.get("data", {}).get("fallback_profile_dir")
            else None
        ),
        fallback_reason=str(payload.get("data", {}).get("fallback_reason") or "") or None,
    )
```

```python
from __future__ import annotations

import asyncio
from typing import Any

from browser_cli.daemon.client import send_command
from browser_cli.profiles.discovery import ChromeEnvironment
from browser_cli.task_runtime.models import SnapshotResult
from browser_cli.task_runtime.read import ReadRequest, ReadResult, run_read_request


class BrowserCliTaskClient:
    def __init__(self, *, chrome_environment: ChromeEnvironment | None = None) -> None:
        self._chrome_environment = chrome_environment

    def invoke(self, action: str, **args: Any) -> dict[str, Any]:
        response = send_command(action, args)
        return dict(response.get("data") or {})

    def read(
        self,
        url: str,
        *,
        output_mode: str = "html",
        scroll_bottom: bool = False,
    ) -> ReadResult:
        return asyncio.run(
            run_read_request(
                ReadRequest(
                    url=url,
                    output_mode=output_mode,
                    scroll_bottom=scroll_bottom,
                ),
                chrome_environment=self._chrome_environment,
            )
        )
```

```python
from browser_cli.task_runtime.read import ReadResult


def read(
    self,
    url: str,
    *,
    output_mode: str = "html",
    scroll_bottom: bool = False,
) -> ReadResult:
    return self.client.read(url, output_mode=output_mode, scroll_bottom=scroll_bottom)
```

```python
from browser_cli.task_runtime.read import ReadResult

__all__ = [
    "BrowserCliTaskClient",
    "Flow",
    "FlowContext",
    "ReadResult",
    "SnapshotRef",
    "SnapshotResult",
    "load_task_entrypoint",
    "parse_input_overrides",
    "run_task_entrypoint",
    "validate_task_dir",
    "validate_task_metadata",
]
```

- [ ] **Step 4: Run the task runtime read unit tests to verify they pass**

Run: `pytest tests/unit/test_task_runtime_client_read.py -q`
Expected: PASS

- [ ] **Step 5: Commit the shared task runtime read task**

```bash
git add src/browser_cli/task_runtime/read.py src/browser_cli/task_runtime/client.py src/browser_cli/task_runtime/flow.py src/browser_cli/task_runtime/__init__.py tests/unit/test_task_runtime_client_read.py
git commit -m "feat: unify one-shot read in task runtime"
```

### Task 2: Switch CLI Read To The Unified Runtime Path

**Files:**
- Modify: `src/browser_cli/commands/read.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Update the CLI tests to target `BrowserCliTaskClient.read(...)`**

```python
from __future__ import annotations

from unittest.mock import patch

from browser_cli.cli.main import main
from browser_cli.errors import ProfileUnavailableError
from browser_cli.task_runtime.read import ReadResult


def test_read_command_normalizes_url_before_client_read(capsys) -> None:
    with patch(
        "browser_cli.commands.read.BrowserCliTaskClient.read",
        return_value=ReadResult(body="ok"),
    ) as mock_read:
        exit_code = main(["read", "example.com"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "ok"
    mock_read.assert_called_once_with(
        "https://example.com",
        output_mode="html",
        scroll_bottom=False,
    )


def test_fallback_profile_reports_to_stderr(capsys) -> None:
    with patch(
        "browser_cli.commands.read.BrowserCliTaskClient.read",
        return_value=ReadResult(
            body="ok",
            used_fallback_profile=True,
            fallback_profile_dir="/tmp/browser-cli/default-profile",
            fallback_reason="Chrome profile appears to be in use.",
        ),
    ):
        exit_code = main(["read", "https://example.com"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "ok"
    assert "using fallback profile" in captured.err
```

- [ ] **Step 2: Run the CLI tests to verify they fail**

Run: `pytest tests/unit/test_cli.py -q`
Expected: FAIL because `tests/unit/test_cli.py` still imports `ReadResult` from `browser_cli.runtime.read_runner` and `commands/read.py` still patches `ReadRunner.run`.

- [ ] **Step 3: Update `commands/read.py` to use `BrowserCliTaskClient.read(...)`**

```python
"""Read command handler."""

from __future__ import annotations

import sys
from argparse import Namespace

from browser_cli.outputs.render import render_output
from browser_cli.task_runtime import BrowserCliTaskClient


def normalize_url(url: str) -> str:
    if "://" in url:
        return url
    return f"https://{url}"


def run_read_command(args: Namespace) -> str:
    client = BrowserCliTaskClient()
    result = client.read(
        normalize_url(args.url),
        output_mode="snapshot" if args.snapshot else "html",
        scroll_bottom=bool(args.scroll_bottom),
    )
    if result.used_fallback_profile and result.fallback_profile_dir:
        message = (
            "Info: primary Chrome profile unavailable; using fallback profile at "
            f"{result.fallback_profile_dir}"
        )
        if result.fallback_reason:
            message += f". Reason: {result.fallback_reason}"
        sys.stderr.write(message + "\n")
    return render_output(result.body)
```

- [ ] **Step 4: Run the CLI tests again**

Run: `pytest tests/unit/test_cli.py -q`
Expected: PASS

- [ ] **Step 5: Commit the CLI unification task**

```bash
git add src/browser_cli/commands/read.py tests/unit/test_cli.py
git commit -m "refactor: route cli read through task runtime"
```

### Task 3: Remove The Legacy Runtime Package And Port Integration Coverage

**Files:**
- Delete: `src/browser_cli/runtime/read_runner.py`
- Delete: `src/browser_cli/runtime/__init__.py`
- Delete: `tests/integration/test_read_runner.py`
- Create: `tests/integration/test_task_runtime_read.py`

- [ ] **Step 1: Port the integration tests to `BrowserCliTaskClient.read(...)`**

```python
from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

import pytest
from tests.integration.fixture_server import run_fixture_server

from browser_cli.daemon.client import send_command
from browser_cli.profiles.discovery import ChromeEnvironment
from browser_cli.task_runtime.client import BrowserCliTaskClient


def _can_launch_playwright_browser() -> bool:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False

    async def _probe() -> bool:
        playwright = await async_playwright().start()
        try:
            browser = await playwright.chromium.launch(headless=True)
            await browser.close()
            return True
        except Exception:
            return False
        finally:
            await playwright.stop()

    return asyncio.run(_probe())


pytestmark = pytest.mark.integration


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _configure_runtime(monkeypatch, tmp_path: Path) -> None:
    real_home = Path.home()
    if not (
        real_home / "Library" / "Caches" / "ms-playwright"
    ).exists() and sys.platform.startswith("linux"):
        playwright_cache = real_home / ".cache" / "ms-playwright"
    else:
        playwright_cache = real_home / "Library" / "Caches" / "ms-playwright"
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(playwright_cache))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / ".browser-cli-runtime"))
    monkeypatch.setenv("X_AGENT_ID", "read-agent")
    monkeypatch.setenv("BROWSER_CLI_HEADLESS", "1")
    monkeypatch.setenv("BROWSER_CLI_EXTENSION_PORT", str(_unused_port()))


def _build_chrome_environment(tmp_path: Path) -> ChromeEnvironment:
    user_data_dir = tmp_path / "user-data"
    (user_data_dir / "Default").mkdir(parents=True)
    return ChromeEnvironment(
        executable_path=None,
        user_data_dir=user_data_dir,
        profile_directory="Default",
    )


def _serialize_environment(chrome_environment: ChromeEnvironment) -> dict[str, str | None]:
    return {
        "executable_path": (
            str(chrome_environment.executable_path)
            if chrome_environment.executable_path is not None
            else None
        ),
        "user_data_dir": str(chrome_environment.user_data_dir),
        "profile_directory": chrome_environment.profile_directory,
        "profile_name": chrome_environment.profile_name,
        "source": chrome_environment.source,
        "fallback_reason": chrome_environment.fallback_reason,
    }


@pytest.mark.skipif(
    not _can_launch_playwright_browser(), reason="Playwright browser runtime unavailable"
)
def test_task_runtime_read_capture_html_from_dynamic_fixture(monkeypatch, tmp_path: Path) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    client = BrowserCliTaskClient(chrome_environment=_build_chrome_environment(tmp_path))
    with run_fixture_server() as base_url:
        result = client.read(f"{base_url}/dynamic", output_mode="html")
        assert "Dynamic Fixture" in result.body
        assert "Rendered content." in result.body

        tabs = send_command("tabs", start_if_needed=False)
        assert tabs["data"]["tabs"] == []
        send_command("stop", start_if_needed=False)


@pytest.mark.skipif(
    not _can_launch_playwright_browser(), reason="Playwright browser runtime unavailable"
)
def test_task_runtime_read_capture_snapshot_from_static_fixture(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    client = BrowserCliTaskClient(chrome_environment=_build_chrome_environment(tmp_path))
    with run_fixture_server() as base_url:
        result = client.read(f"{base_url}/static", output_mode="snapshot")
        assert "heading" in result.body
        assert "Static Fixture" in result.body
        send_command("stop", start_if_needed=False)


@pytest.mark.skipif(
    not _can_launch_playwright_browser(), reason="Playwright browser runtime unavailable"
)
def test_task_runtime_read_scroll_bottom_loads_more_content_without_leaking_tabs(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    chrome_environment = _build_chrome_environment(tmp_path)
    client = BrowserCliTaskClient(chrome_environment=chrome_environment)
    with run_fixture_server() as base_url:
        existing_page = send_command(
            "open",
            {
                "url": f"{base_url}/static",
                "chrome_environment": _serialize_environment(chrome_environment),
            },
        )
        existing_page_id = existing_page["data"]["page"]["page_id"]

        result = client.read(
            f"{base_url}/lazy",
            output_mode="html",
            scroll_bottom=True,
        )
        assert "Lazy Item 4" in result.body

        tabs = send_command("tabs", start_if_needed=False)
        assert [tab["page_id"] for tab in tabs["data"]["tabs"]] == [existing_page_id]
        send_command("stop", start_if_needed=False)
```

- [ ] **Step 2: Remove the legacy package files once callers are migrated**

Run:

```bash
git rm src/browser_cli/runtime/read_runner.py src/browser_cli/runtime/__init__.py tests/integration/test_read_runner.py
```

Expected: the legacy runtime package and the `ReadRunner`-named integration file are staged for deletion.

- [ ] **Step 3: Run the targeted integration and import checks**

Run: `pytest tests/integration/test_task_runtime_read.py -q`
Expected: PASS on a machine with the Playwright browser runtime installed, otherwise SKIPPED with `Playwright browser runtime unavailable`.

Run: `rg -n "browser_cli\\.runtime|ReadRunner" src tests -g '!src/browser_cli/runtime/__pycache__/**'`
Expected: no matches.

- [ ] **Step 4: Commit the runtime-package removal task**

```bash
git add tests/integration/test_task_runtime_read.py
git commit -m "refactor: remove legacy runtime read package"
```

### Task 4: Update Durable Docs And Agent Guidance

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/examples/task-and-automation.md`

- [ ] **Step 1: Update the durable guidance surfaces**

```md
- One-shot read contract, URL normalization, and Python runtime entrypoint:
  `src/browser_cli/commands/read.py`, `src/browser_cli/task_runtime/client.py`, `src/browser_cli/task_runtime/read.py`
- `browser_cli.task_runtime` owns the public Python runtime surface, including one-shot read orchestration reused by `task.py`, automation execution, and CLI `read`.
```

```md
- If the user wants to change `read` behavior:
  inspect `src/browser_cli/commands/read.py`, `src/browser_cli/task_runtime/read.py`, and `src/browser_cli/daemon/browser_service.py::read_page`.
```

```md
- `browser_cli.task_runtime` owns the public Python runtime used by `task.py`, including one-shot read orchestration and flow helpers.
```

````md
## One-Shot Read Pattern

Use `Flow.read(...)` when a task wants the same one-shot behavior as CLI `read`:
````

```python
from browser_cli.task_runtime.flow import Flow


def run(flow: Flow, inputs: dict) -> dict:
    result = flow.read(inputs["url"], output_mode="snapshot", scroll_bottom=True)
    return {"snapshot": result.body}
```

- [ ] **Step 2: Verify the durable docs no longer point at the removed package**

Run: `rg -n "runtime/read_runner|browser_cli\\.runtime\\.read_runner" AGENTS.md docs/examples src/browser_cli tests/unit tests/integration`
Expected: no matches.

- [ ] **Step 3: Run full repository validation**

Run: `scripts/lint.sh`
Expected: PASS

Run: `scripts/test.sh`
Expected: PASS

Run: `scripts/guard.sh`
Expected: PASS

- [ ] **Step 4: Commit the docs and guidance update**

```bash
git add AGENTS.md docs/examples/task-and-automation.md
git commit -m "docs: align guidance with unified task runtime read"
```
