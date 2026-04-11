"""Run all repository guards."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.guards.architecture import run as run_architecture_guard
from scripts.guards.common import Finding, format_findings, repo_root
from scripts.guards.docs_sync import run as run_docs_guard
from scripts.guards.product_contracts import run as run_product_guard


def main() -> int:
    root = repo_root()
    findings: list[Finding] = []
    findings.extend(run_architecture_guard(root))
    findings.extend(run_product_guard(root))
    findings.extend(run_docs_guard(root))

    print(format_findings(findings))
    has_errors = any(finding.level == "error" for finding in findings)
    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
