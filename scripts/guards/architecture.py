"""Static architecture guard checks."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.guards.common import (
    Finding,
    discover_top_level_packages,
    iter_python_files,
    owning_package,
    resolve_internal_imports,
    source_root,
    top_level_target,
)

SHARED_IMPORTS = {
    "browser_cli",
    "browser_cli.constants",
    "browser_cli.error_codes",
    "browser_cli.errors",
    "browser_cli.exit_codes",
}

ALLOWED_DEPENDENCIES: dict[str, set[str]] = {
    "actions": set(),
    "agent_scope": {"constants"},
    "automation": {"automation", "errors", "task_runtime"},
    "browser": {"browser", "constants", "errors", "network", "profiles", "refs"},
    "cli": {"actions", "commands", "errors", "exit_codes"},
    "commands": {"automation", "daemon", "errors", "outputs", "runtime", "task_runtime"},
    "daemon": {
        "agent_scope",
        "browser",
        "constants",
        "drivers",
        "error_codes",
        "errors",
        "extension",
        "profiles",
        "refs",
        "tabs",
    },
    "drivers": {"browser", "errors", "extension", "profiles", "refs"},
    "extension": {"constants", "errors", "extension"},
    "outputs": set(),
    "profiles": {"errors"},
    "refs": {"refs"},
    "runtime": {"daemon", "errors", "profiles"},
    "tabs": {"constants", "errors"},
    "task_runtime": {"daemon", "errors", "task_runtime"},
}


def run(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    packages = discover_top_level_packages(root)
    unknown_packages = sorted(packages - ALLOWED_DEPENDENCIES.keys())
    if unknown_packages:
        findings.append(
            Finding(
                "error",
                "ARCH001",
                "New top-level packages must be added to the architecture guard map: "
                + ", ".join(unknown_packages),
            )
        )

    for path in iter_python_files(source_root(root)):
        owner = owning_package(path, root)
        if owner is None or owner not in ALLOWED_DEPENDENCIES:
            continue
        allowed_targets = ALLOWED_DEPENDENCIES[owner]
        for import_name in sorted(resolve_internal_imports(path)):
            if import_name in SHARED_IMPORTS:
                continue
            target = top_level_target(import_name)
            if target == owner:
                continue
            if target in allowed_targets:
                continue
            findings.append(
                Finding(
                    "error",
                    "ARCH002",
                    f"{path.relative_to(root)} imports {import_name}, which crosses the allowed boundary for browser_cli.{owner}.",
                )
            )
            continue
        if owner != "browser":
            for import_name in sorted(resolve_internal_imports(path)):
                if import_name == "browser_cli.browser.session" or import_name.startswith(
                    "browser_cli.browser.session."
                ):
                    findings.append(
                        Finding(
                            "error",
                            "ARCH003",
                            f"{path.relative_to(root)} must not depend on browser_cli.browser.session. Route browser access through daemon/browser service layers instead.",
                        )
                    )
        if owner == "drivers":
            findings.extend(_check_driver_contracts(path, root))
    return findings


def _check_driver_contracts(path: Path, root: Path) -> list[Finding]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name == "capture_snapshot":
            findings.append(
                Finding(
                    "error",
                    "ARCH004",
                    f"{path.relative_to(root)} defines capture_snapshot(). Drivers must only expose capture_snapshot_input() and leave final snapshot formatting to daemon-owned refs.",
                )
            )
        positional_args = [arg.arg for arg in node.args.args]
        kwonly_args = [arg.arg for arg in node.args.kwonlyargs]
        if "ref" in {*positional_args, *kwonly_args}:
            findings.append(
                Finding(
                    "error",
                    "ARCH005",
                    f"{path.relative_to(root)} exposes a raw 'ref' parameter in {node.name}(). Drivers must consume daemon-built locator specs instead of raw refs.",
                )
            )
    return findings
