from __future__ import annotations

from unittest.mock import patch

from browser_cli.cli.main import main
from browser_cli.errors import ProfileUnavailableError


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
