"""Static Python compatibility guard for the repository baseline."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.guards.common import Finding, format_findings, iter_python_files, repo_root

TARGET_MINOR = 10
CHECK_ROOTS = ("src", "tests", "scripts")


def run(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for relative in CHECK_ROOTS:
        base = root / relative
        if not base.exists():
            continue
        for path in iter_python_files(base):
            findings.extend(_check_file(path))
    return findings


def _check_file(path: Path) -> list[Finding]:
    source = path.read_text(encoding="utf-8")
    findings: list[Finding] = []
    try:
        tree = ast.parse(source, filename=str(path), feature_version=TARGET_MINOR)
    except SyntaxError as exc:
        findings.append(
            Finding(
                "error",
                "PY310001",
                f"{path}: Python 3.10 syntax check failed: {exc.msg} (line {exc.lineno})",
            )
        )
        return findings

    findings.extend(_check_datetime_utc_usage(path, tree))
    return findings


def _check_datetime_utc_usage(path: Path, tree: ast.AST) -> list[Finding]:
    findings: list[Finding] = []
    datetime_module_names = {"datetime"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "datetime":
                    datetime_module_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module != "datetime":
                continue
            for alias in node.names:
                if alias.name == "UTC":
                    findings.append(
                        Finding(
                            "error",
                            "PY310002",
                            f"{path}:{node.lineno}: datetime.UTC is unavailable on Python 3.10; use timezone.utc instead.",
                        )
                    )
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in datetime_module_names
            and node.attr == "UTC"
        ):
            findings.append(
                Finding(
                    "error",
                    "PY310002",
                    f"{path}:{node.lineno}: datetime.UTC is unavailable on Python 3.10; use timezone.utc instead.",
                )
            )
    return findings


def main() -> int:
    findings = run(repo_root())
    print(format_findings(findings))
    has_errors = any(finding.level == "error" for finding in findings)
    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
