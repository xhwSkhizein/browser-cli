from __future__ import annotations

from pathlib import Path

from scripts.guards.python_compatibility import run as run_python_compat_guard


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_python_compat_guard_passes_for_current_repo() -> None:
    findings = run_python_compat_guard(Path.cwd())
    assert findings == []


def test_python_compat_guard_rejects_python_312_syntax(tmp_path: Path) -> None:
    root = tmp_path
    _write_file(root / "src" / "browser_cli" / "demo.py", "type Alias = int\n")

    findings = run_python_compat_guard(root)

    assert [finding.code for finding in findings] == ["PY310001"]
    assert "Python 3.10 syntax" in findings[0].message


def test_python_compat_guard_rejects_datetime_utc_import(tmp_path: Path) -> None:
    root = tmp_path
    _write_file(
        root / "src" / "browser_cli" / "demo.py",
        "from datetime import UTC\nvalue = UTC\n",
    )

    findings = run_python_compat_guard(root)

    assert [finding.code for finding in findings] == ["PY310002"]
    assert "timezone.utc" in findings[0].message
