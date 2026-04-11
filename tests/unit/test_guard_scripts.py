from __future__ import annotations

from scripts.guards.architecture import run as run_architecture_guard
from scripts.guards.docs_sync import run as run_docs_guard
from scripts.guards.product_contracts import run as run_product_guard
from scripts.guards.run_all import main as run_all_guards
from scripts.guards.common import repo_root


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
