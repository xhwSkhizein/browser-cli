from __future__ import annotations

import scripts.guards.run_all as guard_runner
from scripts.guards.architecture import run as run_architecture_guard
from scripts.guards.common import repo_root
from scripts.guards.docs_sync import run as run_docs_guard
from scripts.guards.product_contracts import run as run_product_guard
from scripts.guards.run_all import main as run_all_guards


def test_architecture_guard_passes_for_current_repo() -> None:
    findings = run_architecture_guard(repo_root())
    assert findings == []


def test_product_contract_guard_passes_for_current_repo() -> None:
    findings = run_product_guard(repo_root())
    assert findings == []


def test_docs_sync_guard_passes_for_current_repo() -> None:
    findings = run_docs_guard(repo_root())
    assert findings == []


def test_guard_runner_exits_cleanly_for_current_repo() -> None:
    assert run_all_guards() == 0


def test_guard_runner_includes_python_compatibility_guard(monkeypatch, capsys) -> None:
    monkeypatch.setattr(guard_runner, "run_architecture_guard", lambda _root: [])
    monkeypatch.setattr(guard_runner, "run_product_guard", lambda _root: [])
    monkeypatch.setattr(guard_runner, "run_docs_guard", lambda _root: [])
    monkeypatch.setattr(
        guard_runner,
        "run_python_compatibility_guard",
        lambda _root: [
            guard_runner.Finding(
                "error",
                "PY310999",
                "synthetic python compatibility failure",
            )
        ],
    )

    exit_code = guard_runner.main()

    assert exit_code == 1
    assert "PY310999" in capsys.readouterr().out


def test_lint_script_runs_python_compatibility_guard() -> None:
    script = (repo_root() / "scripts" / "lint.sh").read_text(encoding="utf-8")
    assert "python_compatibility.py" in script
    assert "uv run ruff check src tests scripts" in script
    assert "uv run ruff format --check src tests scripts" in script


def test_repository_scripts_require_uv_and_do_not_fallback_to_pip_or_python() -> None:
    for script_name in ("lint.sh", "test.sh", "guard.sh"):
        script = (repo_root() / "scripts" / script_name).read_text(encoding="utf-8")
        assert "command -v uv >/dev/null 2>&1" in script
        assert "uv is required" in script
        assert ".venv/bin/python" not in script
        assert "python or python3 is required" not in script
        assert "python -m pip" not in script


def test_test_and_guard_scripts_execute_through_uv() -> None:
    test_script = (repo_root() / "scripts" / "test.sh").read_text(encoding="utf-8")
    guard_script = (repo_root() / "scripts" / "guard.sh").read_text(encoding="utf-8")
    assert "uv sync --dev --reinstall-package browser-cli" in test_script
    assert "uv run pytest -q" in test_script
    assert "uv run python scripts/guards/run_all.py" in guard_script
