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
    assert "browserctl" in doctor_text or "uv sync --dev" in doctor_text


def test_uninstall_doc_is_linked_from_primary_install_docs() -> None:
    uninstall_text = _read("docs/uninstall.md")
    readme_text = _read("README.md")
    uv_doc_text = _read("docs/installed-with-uv.md")

    assert "# Uninstall Browser CLI" in uninstall_text
    assert "browser-cli paths" in uninstall_text
    assert "browser-cli automation stop" in uninstall_text
    assert "browser-cli reload" in uninstall_text
    assert "uv tool uninstall browserctl" in uninstall_text
    assert "docs/uninstall.md" in readme_text
    assert "docs/uninstall.md" in uv_doc_text
