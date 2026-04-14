# Browser CLI Install Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `browser-cli install-skills` install exactly the three Browser CLI skills from wheel-packaged assets, with `--target` support and release-artifact validation.

**Architecture:** Move the release-backed skill assets under `src/browser_cli/packaged_skills/` so the installed wheel owns the runtime source of truth. Replace the current path-guessing logic in `install_skills.py` with `importlib.resources`-based discovery plus a fixed public whitelist, document the new package and `install-skills --target` contract in `AGENTS.md`, and lock the behavior with command tests, guard expectations, and a build-artifact smoke check.

**Tech Stack:** Python 3.10, `importlib.resources`, `argparse`, `shutil`, `pytest`, uv build/install workflows, GitHub Actions

---

## File Map

- Create: `src/browser_cli/packaged_skills/__init__.py`
  Responsibility: mark packaged skill assets as a Python package addressable through `importlib.resources`.
- Create: `src/browser_cli/packaged_skills/browser-cli-delivery/SKILL.md`
  Responsibility: packaged runtime copy of the public delivery skill.
- Create: `src/browser_cli/packaged_skills/browser-cli-explore/SKILL.md`
  Responsibility: packaged runtime copy of the public explore skill.
- Create: `src/browser_cli/packaged_skills/browser-cli-converge/SKILL.md`
  Responsibility: packaged runtime copy of the public converge skill.
- Modify: `src/browser_cli/commands/install_skills.py`
  Responsibility: replace repository/pip heuristics with packaged whitelist discovery, `--target` support, and fail-fast validation.
- Modify: `src/browser_cli/cli/main.py`
  Responsibility: expose `--target` on the top-level command and keep help text aligned with the new contract.
- Modify: `AGENTS.md`
  Responsibility: document the `browser_cli.packaged_skills` package and the public `browser-cli install-skills --target` behavior in the repo navigation guide.
- Modify: `pyproject.toml`
  Responsibility: ensure packaged skill assets are included in the wheel.
- Modify: `scripts/guards/architecture.py`
  Responsibility: whitelist the new `browser_cli.packaged_skills` top-level package boundary.
- Modify: `scripts/guards/docs_sync.py`
  Responsibility: require the maintained `install-skills --target` AGENTS.md contract text.
- Create: `tests/unit/test_install_skills_command.py`
  Responsibility: cover whitelist discovery, install/update behavior, `--target`, and failure paths.
- Modify: `tests/unit/test_cli.py`
  Responsibility: assert `install-skills --help` exposes `--target`.
- Modify: `tests/unit/test_repo_skill_docs.py`
  Responsibility: lock the `packaged_skills` architecture entry and packaged skill doc sync expectations.
- Modify: `tests/unit/test_repo_metadata.py`
  Responsibility: lock packaging metadata needed for packaged skill assets.
- Create: `tests/unit/test_release_artifacts.py`
  Responsibility: inspect the built wheel and verify it contains the three packaged skills.
- Modify: `.github/workflows/ci.yml`
  Responsibility: run the artifact smoke test in CI so wheel regressions fail before release.
- Modify: `.github/workflows/release.yml`
  Responsibility: run the same build-artifact smoke before `uv publish`.
- Modify: `docs/superpowers/plans/2026-04-14-browser-cli-install-skills-implementation-plan.md`
  Responsibility: update checkbox state during execution if this plan is used as the live log.

## Task 1: Package The Three Public Skills Inside `browser_cli`

**Files:**
- Create: `src/browser_cli/packaged_skills/__init__.py`
- Create: `src/browser_cli/packaged_skills/browser-cli-delivery/SKILL.md`
- Create: `src/browser_cli/packaged_skills/browser-cli-explore/SKILL.md`
- Create: `src/browser_cli/packaged_skills/browser-cli-converge/SKILL.md`
- Modify: `pyproject.toml`
- Modify: `tests/unit/test_repo_metadata.py`
- Test: `tests/unit/test_repo_metadata.py`

- [ ] **Step 1: Write the failing packaging metadata test**

Append to `tests/unit/test_repo_metadata.py`:

```python
def test_repo_includes_packaged_browser_cli_skills_in_wheel_config() -> None:
    data = _load_pyproject()

    package_data = data["tool"]["setuptools"].get("package-data", {})
    assert "browser_cli.packaged_skills" in package_data
    assert package_data["browser_cli.packaged_skills"] == ["**/SKILL.md"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_repo_metadata.py::test_repo_includes_packaged_browser_cli_skills_in_wheel_config -v
```

Expected: FAIL because `tool.setuptools.package-data` is not defined yet.

- [ ] **Step 3: Add the packaged skill package and wheel metadata**

Create `src/browser_cli/packaged_skills/__init__.py`:

```python
"""Packaged Browser CLI skills shipped with the installed distribution."""
```

Create `src/browser_cli/packaged_skills/browser-cli-delivery/SKILL.md` by copying the current public source skill:

```markdown
---
name: browser-cli-delivery
description: Orchestrate Browser CLI exploration, convergence, validation, and optional automation packaging for reusable web tasks.
---

# Browser CLI Delivery

## Overview

Use this as the main entrypoint when the user wants a reusable Browser CLI web
task rather than one-off browsing. The default endpoint is stable
`task.py + task.meta.json`. `automation.toml` generation and publish are
optional user-driven branches.
```

Create `src/browser_cli/packaged_skills/browser-cli-explore/SKILL.md`:

```markdown
---
name: browser-cli-explore
description: Explore real websites with Browser CLI, validate task mode, and distill durable feedback into task metadata.
---

# Browser CLI Explore

## Overview

Use `browser-cli` to explore a site, test candidate paths, and distill only the
durable findings needed to build a reusable task. The primary output of this
skill is structured knowledge in `task.meta.json`, not final task code.
```

Create `src/browser_cli/packaged_skills/browser-cli-converge/SKILL.md`:

```markdown
---
name: browser-cli-converge
description: Turn validated Browser CLI exploration into stable task.py execution logic and task validation.
---

# Browser CLI Converge

## Overview

Use this skill after exploration has already validated the success path. Its
job is to encode that evidence into stable `task.py` logic and keep the
implementation aligned with `task.meta.json`.
```

Update `pyproject.toml`:

```toml
[tool.setuptools]
package-dir = {"" = "src"}
include-package-data = true

[tool.setuptools.package-data]
"browser_cli.packaged_skills" = ["**/SKILL.md"]
```

- [ ] **Step 4: Run the metadata test to verify it passes**

Run:

```bash
uv run pytest tests/unit/test_repo_metadata.py::test_repo_includes_packaged_browser_cli_skills_in_wheel_config -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/unit/test_repo_metadata.py src/browser_cli/packaged_skills
git commit -m "build: package browser-cli skills in wheel"
```

## Task 2: Replace Runtime Skill Discovery With A Packaged Whitelist

**Files:**
- Modify: `src/browser_cli/commands/install_skills.py`
- Create: `tests/unit/test_install_skills_command.py`
- Test: `tests/unit/test_install_skills_command.py`

- [ ] **Step 1: Write the failing command tests**

Create `tests/unit/test_install_skills_command.py`:

```python
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from browser_cli.commands import install_skills as install_skills_module
from browser_cli.errors import InvalidInputError


def test_get_skills_target_path_defaults_to_agents_skills(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert install_skills_module.get_skills_target_path(None) == tmp_path / ".agents" / "skills"


def test_get_skills_target_path_honors_explicit_target(tmp_path: Path) -> None:
    target = tmp_path / "custom-skills"
    assert install_skills_module.get_skills_target_path(str(target)) == target.resolve()


def test_discover_packaged_skills_returns_three_public_skills() -> None:
    discovered = install_skills_module.discover_packaged_skills()
    assert [item.name for item in discovered] == [
        "browser-cli-converge",
        "browser-cli-delivery",
        "browser-cli-explore",
    ]


def test_install_skills_reports_install_and_update(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    for name in ("browser-cli-delivery", "browser-cli-explore", "browser-cli-converge"):
        skill_dir = source_root / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    (target_root / "browser-cli-delivery").mkdir(parents=True)

    results = install_skills_module.install_skills_from_paths(
        [
            install_skills_module.PackagedSkill(name="browser-cli-delivery", path=source_root / "browser-cli-delivery"),
            install_skills_module.PackagedSkill(name="browser-cli-explore", path=source_root / "browser-cli-explore"),
            install_skills_module.PackagedSkill(name="browser-cli-converge", path=source_root / "browser-cli-converge"),
        ],
        target_root,
        dry_run=True,
    )

    assert results == [
        ("browser-cli-delivery", "would update"),
        ("browser-cli-explore", "would install"),
        ("browser-cli-converge", "would install"),
    ]


def test_run_install_skills_command_uses_explicit_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_root = tmp_path / "source"
    packaged = []
    for name in ("browser-cli-delivery", "browser-cli-explore", "browser-cli-converge"):
        skill_dir = source_root / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        packaged.append(install_skills_module.PackagedSkill(name=name, path=skill_dir))
    monkeypatch.setattr(install_skills_module, "discover_packaged_skills", lambda: packaged)

    output = install_skills_module.run_install_skills_command(
        Namespace(dry_run=True, target=str(tmp_path / "custom"))
    )

    assert "Installing skills to" in output
    assert str((tmp_path / "custom").resolve()) in output
    assert "Total: 3 skill(s)" in output
```

- [ ] **Step 2: Run the command tests to verify they fail**

Run:

```bash
uv run pytest tests/unit/test_install_skills_command.py -v
```

Expected: FAIL because `get_skills_target_path(None)`, `discover_packaged_skills()`, `PackagedSkill`, and `install_skills_from_paths()` do not exist yet.

- [ ] **Step 3: Rewrite `install_skills.py` around packaged skill discovery**

Replace `src/browser_cli/commands/install_skills.py` with:

```python
"""Install packaged Browser CLI skills into a target skills directory."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from browser_cli.errors import InvalidInputError

PUBLIC_SKILL_NAMES = (
    "browser-cli-converge",
    "browser-cli-delivery",
    "browser-cli-explore",
)


@dataclass(frozen=True, slots=True)
class PackagedSkill:
    name: str
    path: Path


def discover_packaged_skills() -> list[PackagedSkill]:
    root = resources.files("browser_cli.packaged_skills")
    discovered: list[PackagedSkill] = []
    for name in PUBLIC_SKILL_NAMES:
        skill_root = root.joinpath(name)
        if not skill_root.is_dir():
            raise InvalidInputError(f"Packaged skill is missing from this build: {name}")
        with resources.as_file(skill_root) as skill_path:
            skill_dir = skill_path.resolve()
            if not (skill_dir / "SKILL.md").exists():
                raise InvalidInputError(f"Packaged skill is incomplete in this build: {name}")
            discovered.append(PackagedSkill(name=name, path=skill_dir))
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
        target.mkdir(parents=True, exist_ok=True)
    for skill in skills:
        destination = target / skill.name
        if destination.exists():
            status = "would update" if dry_run else "updated"
        else:
            status = "would install" if dry_run else "installed"
        if not dry_run:
            if destination.exists():
                shutil.rmtree(destination)
            with tempfile.TemporaryDirectory(prefix=f"{skill.name}-") as tmp_dir:
                staged = Path(tmp_dir) / skill.name
                shutil.copytree(skill.path, staged)
                shutil.move(str(staged), destination)
        results.append((skill.name, status))
    return results


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
```

- [ ] **Step 4: Run the command tests to verify they pass**

Run:

```bash
uv run pytest tests/unit/test_install_skills_command.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/browser_cli/commands/install_skills.py tests/unit/test_install_skills_command.py
git commit -m "feat: install packaged browser-cli skills"
```

## Task 3: Expose `--target` And Lock The CLI Contract

**Files:**
- Modify: `src/browser_cli/cli/main.py`
- Modify: `tests/unit/test_cli.py`
- Test: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the failing CLI help test**

Append to `tests/unit/test_cli.py`:

```python
def test_install_skills_help_mentions_target(capsys) -> None:
    exit_code = main(["install-skills", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--dry-run" in captured.out
    assert "--target" in captured.out
    assert "packaged skills" in captured.out.lower()
```

- [ ] **Step 2: Run the CLI help test to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_cli.py::test_install_skills_help_mentions_target -v
```

Expected: FAIL because `--target` is not registered yet.

- [ ] **Step 3: Add the CLI argument and keep help text aligned**

Update the `install-skills` parser block in `src/browser_cli/cli/main.py`:

```python
    skills_parser = subparsers.add_parser(
        "install-skills",
        help="Install packaged Browser CLI skills to a skills directory.",
        description="Copy packaged Browser CLI skills from the installed package to the target skills directory.",
    )
    skills_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be installed without making changes.",
    )
    skills_parser.add_argument(
        "--target",
        help="Optional target directory. Defaults to ~/.agents/skills.",
    )
```

- [ ] **Step 4: Run the CLI help test to verify it passes**

Run:

```bash
uv run pytest tests/unit/test_cli.py::test_install_skills_help_mentions_target -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/browser_cli/cli/main.py tests/unit/test_cli.py
git commit -m "feat: add target override for install-skills"
```

## Task 4: Add Wheel-Artifact Verification

**Files:**
- Create: `tests/unit/test_release_artifacts.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/release.yml`
- Test: `tests/unit/test_release_artifacts.py`

- [ ] **Step 1: Write the failing wheel inspection test**

Create `tests/unit/test_release_artifacts.py`:

```python
from __future__ import annotations

import zipfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_built_wheel_contains_packaged_browser_cli_skills() -> None:
    wheels = sorted((_repo_root() / "dist").glob("*.whl"))
    assert wheels, "Build a wheel before running this test: uv build --wheel"
    wheel_path = wheels[-1]
    with zipfile.ZipFile(wheel_path) as archive:
        names = set(archive.namelist())
    assert "browser_cli/packaged_skills/browser-cli-delivery/SKILL.md" in names
    assert "browser_cli/packaged_skills/browser-cli-explore/SKILL.md" in names
    assert "browser_cli/packaged_skills/browser-cli-converge/SKILL.md" in names
```

- [ ] **Step 2: Build the wheel and run the test to verify it fails**

Run:

```bash
rm -rf dist
uv build --wheel
uv run pytest tests/unit/test_release_artifacts.py::test_built_wheel_contains_packaged_browser_cli_skills -v
```

Expected: FAIL until the wheel metadata and packaged files are fully wired up.

- [ ] **Step 3: Add CI and release smoke steps for built artifacts**

Add this step near the end of `.github/workflows/ci.yml` after the existing unit and integration coverage:

```yaml
  packaging-smoke:
    name: Packaging Smoke
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up uv
        uses: astral-sh/setup-uv@v7
        with:
          python-version-file: .python-version
          enable-cache: true

      - name: Sync dependencies
        run: uv sync --locked --dev

      - name: Build wheel
        run: uv build --wheel --no-sources

      - name: Verify wheel-packaged skills
        run: uv run pytest tests/unit/test_release_artifacts.py -v
```

Insert this step in `.github/workflows/release.yml` before `uv publish`:

```yaml
      - name: Verify wheel-packaged skills
        run: |
          uv build --wheel --no-sources
          uv run pytest tests/unit/test_release_artifacts.py -v
```

- [ ] **Step 4: Rebuild and rerun the artifact test to verify it passes**

Run:

```bash
rm -rf dist
uv build --wheel
uv run pytest tests/unit/test_release_artifacts.py::test_built_wheel_contains_packaged_browser_cli_skills -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_release_artifacts.py .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "test: verify packaged skills in built wheel"
```

## Task 5: Run Full Validation

**Files:**
- Modify: `docs/superpowers/plans/2026-04-14-browser-cli-install-skills-implementation-plan.md`
- Test: `tests/unit/test_install_skills_command.py`
- Test: `tests/unit/test_cli.py`
- Test: `tests/unit/test_repo_metadata.py`
- Test: `tests/unit/test_release_artifacts.py`

- [ ] **Step 1: Run the focused unit and artifact tests**

Run:

```bash
uv run pytest tests/unit/test_repo_metadata.py::test_repo_includes_packaged_browser_cli_skills_in_wheel_config -v
uv run pytest tests/unit/test_install_skills_command.py -v
uv run pytest tests/unit/test_cli.py::test_install_skills_help_mentions_target -v
rm -rf dist
uv build --wheel
uv run pytest tests/unit/test_release_artifacts.py -v
```

Expected: PASS for all commands.

- [ ] **Step 2: Run the repository validation scripts**

Run:

```bash
./scripts/lint.sh
./scripts/test.sh
./scripts/guard.sh
```

Expected: all three scripts exit `0`.

- [ ] **Step 3: Update the plan checklist to reflect completion**

Update this file so completed steps are checked as work lands:

```markdown
- [x] **Step 1: Run the focused unit and artifact tests**
- [x] **Step 2: Run the repository validation scripts**
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-04-14-browser-cli-install-skills-implementation-plan.md
git commit -m "docs: mark install-skills plan execution complete"
```

## Self-Review

Spec coverage check:

- packaged asset source under `src/browser_cli/packaged_skills/`: covered by Task 1
- install only the three public skills: covered by Task 2
- `--target` override with `~/.agents/skills` default: covered by Tasks 2 and 3
- fail-fast behavior for missing packaged assets: covered by Task 2 tests and implementation
- wheel contains packaged skills: covered by Task 4
- CI and release validate built artifacts: covered by Task 4

Placeholder scan:

- no `TODO`, `TBD`, or deferred implementation markers remain
- every task names exact files, commands, and code snippets

Type and naming consistency:

- `PackagedSkill`, `discover_packaged_skills`, `get_skills_target_path`, and `install_skills_from_paths` are introduced in Task 2 and referenced consistently afterward
- the packaged asset path is consistently `src/browser_cli/packaged_skills/`
