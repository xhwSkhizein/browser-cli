from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (_repo_root() / path).read_text(encoding="utf-8")


def test_browser_runtime_hints_point_maintainers_to_uv_sync() -> None:
    session_text = _read("src/browser_cli/browser/session.py")
    service_text = _read("src/browser_cli/browser/service.py")

    assert "python3 -m pip install -e ." not in session_text
    assert "python3 -m pip install -e ." not in service_text
    assert "uv sync --dev" in session_text
    assert "uv sync --dev" in service_text


def test_doctor_command_no_longer_describes_pip_users() -> None:
    doctor_text = _read("src/browser_cli/commands/doctor.py")

    assert '"""Install and runtime diagnostics for pip users."""' not in doctor_text
    assert "uv tool install browser-cli" in doctor_text or "uv sync --dev" in doctor_text
