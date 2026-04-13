"""Command to install bundled skills to the user's skills directory."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def _get_pip_show_location() -> Path | None:
    """Get package installation root from pip show."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "browser-cli"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("Location:"):
                location = line.split(":", 1)[1].strip()
                return Path(location)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None


def _find_git_root() -> Path | None:
    """Find git repository root (for development mode)."""
    import browser_cli

    package_path = Path(browser_cli.__file__).parent
    current = package_path
    while current.parent != current:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def get_skills_source_path() -> Path | None:
    """Get the path to bundled skills.

    Tries pip installation location first, then git root for development.
    """
    # Try pip installation location
    pip_location = _get_pip_show_location()
    if pip_location:
        skills_path = pip_location / "skills"
        if skills_path.exists() and skills_path.is_dir():
            return skills_path

    # Try git root (development mode)
    git_root = _find_git_root()
    if git_root:
        skills_path = git_root / "skills"
        if skills_path.exists() and skills_path.is_dir():
            return skills_path

    return None


def get_skills_target_path() -> Path:
    """Get the target path for skills installation."""
    return Path.home() / ".agents" / "skills"


def install_skills(
    source: Path,
    target: Path,
    dry_run: bool = False,
) -> Sequence[tuple[str, str]]:
    """Install skills from source to target directory.

    Args:
        source: Path to bundled skills directory.
        target: Path to user's skills directory.
        dry_run: If True, only report what would be done.

    Returns:
        List of (skill_name, status) tuples.
    """
    results: list[tuple[str, str]] = []

    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)

    for skill_dir in sorted(source.iterdir()):
        if not skill_dir.is_dir():
            continue

        skill_target = target / skill_dir.name

        if skill_target.exists():
            if dry_run:
                results.append((skill_dir.name, "would update"))
            else:
                shutil.rmtree(skill_target)
                shutil.copytree(skill_dir, skill_target)
                results.append((skill_dir.name, "updated"))
        else:
            if dry_run:
                results.append((skill_dir.name, "would install"))
            else:
                shutil.copytree(skill_dir, skill_target)
                results.append((skill_dir.name, "installed"))

    return results


def run_install_skills_command(args: argparse.Namespace) -> str | None:
    """Run the install-skills command.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Output message to print, or None on failure.
    """
    source = get_skills_source_path()
    if source is None:
        sys.stderr.write("Error: bundled skills not found in package\n")
        return None

    target = get_skills_target_path()

    results = install_skills(source, target, dry_run=args.dry_run)

    if not results:
        return "No skills to install.\n"

    mode = "(dry-run) " if args.dry_run else ""
    lines = [f"{mode}Installing skills to {target}:", ""]

    for skill_name, status in results:
        lines.append(f"  {skill_name}: {status}")

    lines.append("")
    lines.append(f"Total: {len(results)} skill(s)")

    return "\n".join(lines) + "\n"
