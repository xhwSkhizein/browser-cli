"""Install packaged Browser CLI skills into a target skills directory."""

from __future__ import annotations

import argparse
import os
import shutil
import uuid
from dataclasses import dataclass
from importlib import resources
from importlib.abc import Traversable
from pathlib import Path

from browser_cli.errors import InvalidInputError, OperationFailedError

PUBLIC_SKILL_NAMES = (
    "browser-cli-converge",
    "browser-cli-delivery",
    "browser-cli-explore",
)


@dataclass(frozen=True, slots=True)
class PackagedSkill:
    name: str
    source: Traversable | Path


def _packaged_skills_root() -> Traversable:
    return resources.files("browser_cli.packaged_skills")


def discover_packaged_skills() -> list[PackagedSkill]:
    root = _packaged_skills_root()
    discovered: list[PackagedSkill] = []
    for name in PUBLIC_SKILL_NAMES:
        skill_root = root.joinpath(name)
        if not skill_root.is_dir():
            raise InvalidInputError(f"Packaged skill is missing from this build: {name}")
        skill_doc = skill_root.joinpath("SKILL.md")
        if not skill_doc.is_file():
            raise InvalidInputError(
                f"Packaged skill is incomplete in this build: {name} is missing SKILL.md"
            )
        discovered.append(PackagedSkill(name=name, source=skill_root))
    return discovered


def get_skills_target_path(target: str | None) -> Path:
    if target:
        return Path(target).expanduser().resolve()
    return Path.home() / ".agents" / "skills"


def install_skills_from_paths(
    skills: list[PackagedSkill],
    target: Path,
    *,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    if not dry_run:
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OperationFailedError(
                f"Could not create skills target directory {target}: {exc}"
            ) from exc
    for skill in skills:
        destination = target / skill.name
        exists = destination.exists()
        status = (
            "would update"
            if dry_run and exists
            else "would install"
            if dry_run
            else "updated"
            if exists
            else "installed"
        )
        if not dry_run:
            _install_one_skill(skill, destination)
        results.append((skill.name, status))
    return results


def _install_one_skill(skill: PackagedSkill, destination: Path) -> None:
    source = skill.source if isinstance(skill.source, Traversable) else Path(skill.source)
    staged = destination.with_name(f"{destination.name}.tmp-{uuid.uuid4().hex}")
    try:
        _copy_skill_tree(source, staged)
        backup = _swap_staged_directory(staged, destination)
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
    except OSError as exc:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
        raise OperationFailedError(
            f"Could not install skill {skill.name} to {destination}: {exc}"
        ) from exc


def _copy_skill_tree(source: Traversable | Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for child in source.iterdir():
        child_destination = destination / child.name
        if child.is_dir():
            _copy_skill_tree(child, child_destination)
            continue
        with child.open("rb") as handle, child_destination.open("wb") as output:
            shutil.copyfileobj(handle, output)


def _swap_staged_directory(staged: Path, destination: Path) -> Path | None:
    backup: Path | None = None
    if destination.exists():
        backup = destination.with_name(f"{destination.name}.bak-{uuid.uuid4().hex}")
        os.replace(destination, backup)
    try:
        os.replace(staged, destination)
    except OSError:
        if backup is not None and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    return backup


def run_install_skills_command(args: argparse.Namespace) -> str:
    skills = discover_packaged_skills()
    target = get_skills_target_path(getattr(args, "target", None))
    results = install_skills_from_paths(skills, target, dry_run=bool(args.dry_run))
    mode = "(dry-run) " if args.dry_run else ""
    lines = [f"{mode}Installing skills to {target}:", ""]
    for skill_name, status in results:
        lines.append(f"  {skill_name}: {status}")
    lines.append("")
    lines.append(f"Total: {len(results)} skill(s)")
    return "\n".join(lines) + "\n"
