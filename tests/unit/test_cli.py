from __future__ import annotations

import json
from unittest.mock import patch

from browser_cli.cli.main import main
from browser_cli.errors import ChromeExecutableNotFoundError, ProfileUnavailableError
from browser_cli.task_runtime.read import ReadResult


def test_top_level_help(capsys) -> None:
    exit_code = main(["--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "browser-cli" in captured.out
    assert "read" in captured.out
    assert "doctor" in captured.out
    assert "paths" in captured.out
    assert "task" in captured.out
    assert "automation" in captured.out
    assert "status" in captured.out
    assert "open" in captured.out
    assert "click" in captured.out


def test_read_help(capsys) -> None:
    exit_code = main(["read", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "One-shot content-first capture" in captured.out
    assert "interactive exploration" in captured.out
    assert "--snapshot" in captured.out
    assert "--scroll-bottom" in captured.out


def test_snapshot_help_mentions_smaller_capture_options(capsys) -> None:
    exit_code = main(["snapshot", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ref-driven exploration" in captured.out
    assert "Use -i/-F to keep captures smaller" in captured.out
    assert "--interactive" in captured.out
    assert "--no-full-page" in captured.out


def test_click_help(capsys) -> None:
    exit_code = main(["click", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Element ref" in captured.out


def test_status_help(capsys) -> None:
    exit_code = main(["status", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "runtime state" in captured.out
    assert "--json" in captured.out


def test_doctor_help_mentions_json(capsys) -> None:
    exit_code = main(["doctor", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--json" in captured.out
    assert "diagnose" in captured.out.lower()


def test_paths_help_mentions_json(capsys) -> None:
    exit_code = main(["paths", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--json" in captured.out
    assert "runtime paths" in captured.out.lower()


def test_task_help_lists_examples_and_template(capsys) -> None:
    exit_code = main(["task", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "examples" in captured.out
    assert "template" in captured.out
    assert "local editable source" in captured.out


def test_task_template_help_mentions_print(capsys) -> None:
    exit_code = main(["task", "template", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--print" in captured.out


def test_automation_help_lists_observability_commands(capsys) -> None:
    exit_code = main(["automation", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "list" in captured.out
    assert "versions" in captured.out
    assert "inspect" in captured.out
    assert "published immutable snapshot" in captured.out


def test_page_reload_help(capsys) -> None:
    exit_code = main(["page-reload", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Reload the current active tab" in captured.out


def test_missing_command_returns_usage_error(capsys) -> None:
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "usage:" in captured.out


def test_runtime_error_maps_to_stderr_and_exit_code(capsys) -> None:
    with patch(
        "browser_cli.cli.main.run_read_command",
        side_effect=ProfileUnavailableError("profile locked"),
    ):
        exit_code = main(["read", "https://example.com"])

    captured = capsys.readouterr()
    assert exit_code == 73
    assert "profile locked" in captured.err
    assert (
        "Next: close Browser CLI-owned Chrome windows or inspect browser-cli status" in captured.err
    )


def test_json_mode_error_renders_json_to_stdout(capsys) -> None:
    with patch(
        "browser_cli.cli.main.run_doctor_command",
        side_effect=ChromeExecutableNotFoundError("Chrome missing"),
    ):
        exit_code = main(["doctor", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 69
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload == {
        "ok": False,
        "error_code": "CHROME_EXECUTABLE_NOT_FOUND",
        "message": "Chrome missing",
        "next_action": "install stable Google Chrome and re-run browser-cli doctor --json",
    }


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


def test_status_command_renders_report(capsys) -> None:
    with patch("browser_cli.cli.main.run_status_command", return_value="Status: healthy\n"):
        exit_code = main(["status"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "Status: healthy\n"


def test_reload_command_renders_summary(capsys) -> None:
    with patch("browser_cli.cli.main.run_reload_command", return_value="Reload: complete\n"):
        exit_code = main(["reload"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "Reload: complete\n"


def test_workspace_rebuild_help_mentions_json(capsys) -> None:
    exit_code = main(["workspace", "rebuild", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--json" in captured.out
    assert "workspace binding" in captured.out.lower()


def test_recover_help_mentions_json(capsys) -> None:
    exit_code = main(["recover", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--json" in captured.out
    assert "recover" in captured.out.lower()


def test_install_skills_help_mentions_target(capsys) -> None:
    exit_code = main(["install-skills", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--dry-run" in captured.out
    assert "--target" in captured.out
    assert "packaged skills" in captured.out.lower()
