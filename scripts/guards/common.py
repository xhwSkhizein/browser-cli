"""Shared helpers for repository guard scripts."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class Finding:
    level: str
    code: str
    message: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def source_root(root: Path | None = None) -> Path:
    base = root or repo_root()
    return base / "src" / "browser_cli"


def iter_python_files(base: Path) -> Iterable[Path]:
    for path in sorted(base.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def discover_top_level_packages(root: Path | None = None) -> set[str]:
    base = source_root(root)
    packages: set[str] = set()
    for path in sorted(base.iterdir()):
        if not path.is_dir() or path.name == "__pycache__":
            continue
        packages.add(path.name)
    return packages


def owning_package(path: Path, root: Path | None = None) -> str | None:
    base = source_root(root)
    relative = path.relative_to(base)
    if len(relative.parts) <= 1:
        return None
    return relative.parts[0]


def resolve_internal_imports(path: Path, *, package_name: str = "browser_cli") -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_name = _module_name_for_path(path, package_name=package_name)
    is_package = path.name == "__init__.py"
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == package_name or alias.name.startswith(f"{package_name}."):
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_import_from(
                module_name,
                node.level,
                node.module,
                package_name=package_name,
                is_package=is_package,
            )
            if resolved and (resolved == package_name or resolved.startswith(f"{package_name}.")):
                imports.add(resolved)
    return imports


def top_level_target(import_name: str, *, package_name: str = "browser_cli") -> str | None:
    if import_name == package_name:
        return None
    if not import_name.startswith(f"{package_name}."):
        return None
    remainder = import_name[len(package_name) + 1 :]
    return remainder.split(".", 1)[0]


def read_section(markdown_text: str, heading: str) -> str:
    lines = markdown_text.splitlines()
    inside = False
    collected: list[str] = []
    target = f"## {heading}"
    for line in lines:
        if line == target:
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside:
            collected.append(line)
    return "\n".join(collected).strip()


def format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "guard: ok"
    lines: list[str] = []
    for finding in findings:
        lines.append(f"{finding.level.upper()} {finding.code}: {finding.message}")
    return "\n".join(lines)


def _module_name_for_path(path: Path, *, package_name: str) -> str:
    parts = list(path.with_suffix("").parts)
    package_index = parts.index(package_name)
    module_parts = parts[package_index:]
    if module_parts[-1] == "__init__":
        module_parts = module_parts[:-1]
    if not module_parts:
        return package_name
    return ".".join(module_parts)


def _resolve_import_from(
    module_name: str,
    level: int,
    module: str | None,
    *,
    package_name: str,
    is_package: bool,
) -> str | None:
    if level == 0:
        return module
    module_parts = module_name.split(".")
    package_parts = module_parts if is_package else module_parts[:-1]
    if level > len(package_parts):
        return module
    base_parts = package_parts[: len(package_parts) - level + 1]
    if module:
        return ".".join([*base_parts, module])
    return ".".join(base_parts)
