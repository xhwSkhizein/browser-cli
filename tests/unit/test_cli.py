from __future__ import annotations

from unittest.mock import AsyncMock, patch

from browser_cli.cli.main import main
from browser_cli.errors import ProfileUnavailableError
from browser_cli.runtime.read_runner import ReadResult


def test_top_level_help(capsys) -> None:
    exit_code = main(["--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "browser-cli" in captured.out
    assert "read" in captured.out


def test_read_help(capsys) -> None:
    exit_code = main(["read", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--snapshot" in captured.out
    assert "--scroll-bottom" in captured.out


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


def test_fallback_profile_reports_to_stderr(capsys) -> None:
    with patch(
        "browser_cli.commands.read.ReadRunner.run",
        new=AsyncMock(
            return_value=ReadResult(
                body="ok",
                used_fallback_profile=True,
                fallback_profile_dir="/tmp/browser-cli/default-profile",
                fallback_reason="Chrome profile appears to be in use.",
            )
        ),
    ):
        exit_code = main(["read", "https://example.com"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "ok"
    assert "using fallback profile" in captured.err
