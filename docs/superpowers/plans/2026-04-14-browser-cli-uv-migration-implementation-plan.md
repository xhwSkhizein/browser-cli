# Browser CLI UV Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate Browser CLI to a uv-only repository and user workflow so development, CI, release, install docs, and install/recovery hints all converge on uv.

**Architecture:** Keep the existing package/runtime architecture intact and change only the engineering workflow shell around it. Make `pyproject.toml`, `.python-version`, and `uv.lock` the single source of truth for Python and dependency resolution, then route scripts, GitHub Actions, release, docs, and selected user-facing messages through that model without changing CLI product contracts.

**Tech Stack:** Python 3.10+, uv, setuptools, setuptools-scm, pytest, GitHub Actions, Markdown docs, existing repository guards

---

## Scope Note

The approved spec touches multiple operational surfaces, but they are all part
of one bounded migration:

1. repository metadata and lockfile
2. repository shell scripts
3. CI and release workflows
4. docs and durable repo guidance
5. user-facing install and recovery hints

The plan keeps those surfaces in one implementation document, but each task
group lands independently and leaves the repository in a runnable state.

## File Structure

### Create

- `.python-version`
  - Pins the canonical local development Python version to the 3.10 baseline.
- `uv.lock`
  - Repository-controlled dependency lockfile for local development, CI, and release.
- `docs/installed-with-uv.md`
  - New primary installed-user guide for uv-based installation and first-run usage.
- `tests/unit/test_repo_metadata.py`
  - Locks uv project metadata, `.python-version`, and `uv.lock` expectations.
- `tests/unit/test_repo_workflows.py`
  - Locks the CI and release workflows to uv-only behavior.
- `tests/unit/test_repo_text_contracts.py`
  - Locks the repo against stale pip-centric install hints in selected source files.

### Modify

- `pyproject.toml`
  - Move dev-only tooling dependencies into uv dependency groups and mark the dev group as default for local runs.
- `scripts/lint.sh`
  - Require uv and run compile, compatibility, Ruff, and JS checks through `uv run`.
- `scripts/test.sh`
  - Require uv and run pytest through `uv run`.
- `scripts/guard.sh`
  - Require uv and run repository guards through `uv run`.
- `scripts/check.sh`
  - Keep the orchestration surface intact while depending on the uv-only sub-scripts.
- `.github/workflows/ci.yml`
  - Replace pip-based installation with uv setup, uv sync, and uv-run test/lint commands.
- `.github/workflows/release.yml`
  - Replace pip/build/twine setup with uv build and uv publish.
- `README.md`
  - Rewrite installation, quick start, and maintainer workflow sections around uv.
- `docs/installed-with-pip.md`
  - Convert from a primary guide into a short migration note that points users at the new uv guide.
- `AGENTS.md`
  - Record the uv-only repo workflow as durable navigation guidance.
- `scripts/guards/docs_sync.py`
  - Freeze the new uv-first README and AGENTS expectations.
- `tests/unit/test_guard_scripts.py`
  - Lock the uv-only repository script behavior and keep the Python compatibility assertion.
- `src/browser_cli/browser/session.py`
  - Replace the pip-centric missing-Playwright hint with a uv maintainer hint.
- `src/browser_cli/browser/service.py`
  - Replace the pip-centric missing-Playwright hint with a uv maintainer hint.
- `src/browser_cli/commands/doctor.py`
  - Remove stale “pip users” wording and point Playwright recovery guidance at uv.

### Notes

- Do not change the existing `setuptools.build_meta` build backend in this migration.
- Do not change public CLI commands or JSON payloads.
- Do not add a compatibility layer that falls back to bare `python`, `python3`, `.venv/bin/python`, or `pip`.
- Keep `uv.lock` checked in and treat it as a normal reviewed artifact.
- Update `AGENTS.md` because the repository workflow is changing in a durable way.

### Task 1: Adopt UV Project Metadata And Lockfile

**Files:**
- Create: `.python-version`
- Create: `uv.lock`
- Create: `tests/unit/test_repo_metadata.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing repository metadata tests**

```python
from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_pyproject() -> dict[str, object]:
    with (_repo_root() / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_repo_uses_uv_dependency_groups_for_dev_tools() -> None:
    data = _load_pyproject()

    assert data["dependency-groups"]["dev"] == [
        "pytest>=8.0",
        "ruff>=0.4.0",
        "mypy>=1.10.0",
    ]
    assert data["tool"]["uv"]["default-groups"] == ["dev"]
    assert "dev" not in data["project"].get("optional-dependencies", {})


def test_repo_pins_python_version_for_uv() -> None:
    assert (_repo_root() / ".python-version").read_text(encoding="utf-8").strip() == "3.10"


def test_repo_tracks_uv_lockfile() -> None:
    assert (_repo_root() / "uv.lock").exists()
```

- [ ] **Step 2: Run the metadata tests to verify they fail**

Run: `uv run --with pytest --with tomli pytest tests/unit/test_repo_metadata.py -q`
Expected: FAIL because `tests/unit/test_repo_metadata.py` does not exist yet, `.python-version` does not exist, `uv.lock` does not exist, and `pyproject.toml` does not define uv dependency groups.

- [ ] **Step 3: Update `pyproject.toml` for uv-native development**

```toml
[build-system]
requires = ["setuptools>=69", "setuptools-scm>=8.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "browser-cli"
description = "CLI-first browser reader for rendered HTML and page snapshots"
dynamic = ["version"]
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
  "playwright>=1.52,<2",
  "websockets>=12,<16",
  "tomli>=1.2.0; python_version<'3.11'",
]

[project.scripts]
browser-cli = "browser_cli.cli.main:main"

[dependency-groups]
dev = [
  "pytest>=8.0",
  "ruff>=0.4.0",
  "mypy>=1.10.0",
]

[tool.uv]
default-groups = ["dev"]

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools_scm]
# Version is derived from git tags.
```

- [ ] **Step 4: Add the canonical Python pin**

```text
3.10
```

- [ ] **Step 5: Generate and review the lockfile**

Run: `uv lock`
Expected: PASS and create `uv.lock` in the repository root.

- [ ] **Step 6: Run the metadata tests to verify they pass**

Run: `uv run pytest tests/unit/test_repo_metadata.py -q`
Expected: PASS

- [ ] **Step 7: Commit the metadata task**

```bash
git add pyproject.toml .python-version uv.lock tests/unit/test_repo_metadata.py
git commit -m "chore: adopt uv project metadata"
```

### Task 2: Rewrite Repository Scripts For UV-Only Execution

**Files:**
- Modify: `scripts/lint.sh`
- Modify: `scripts/test.sh`
- Modify: `scripts/guard.sh`
- Modify: `scripts/check.sh`
- Modify: `tests/unit/test_guard_scripts.py`

- [ ] **Step 1: Extend the script contract tests to require uv-only behavior**

```python
from pathlib import Path

from scripts.guards.common import repo_root


def _script_text(name: str) -> str:
    return (repo_root() / "scripts" / name).read_text(encoding="utf-8")


def test_lint_script_runs_python_compatibility_guard() -> None:
    script = _script_text("lint.sh")
    assert "python_compatibility.py" in script
    assert "uv run ruff check src tests scripts" in script
    assert "uv run ruff format --check src tests scripts" in script


def test_repository_scripts_require_uv_and_do_not_fallback_to_pip_or_python() -> None:
    for script_name in ("lint.sh", "test.sh", "guard.sh"):
        script = _script_text(script_name)
        assert 'command -v uv >/dev/null 2>&1' in script
        assert "uv is required" in script
        assert ".venv/bin/python" not in script
        assert "python or python3 is required" not in script
        assert "python -m pip" not in script


def test_test_and_guard_scripts_execute_through_uv() -> None:
    assert "uv run pytest -q" in _script_text("test.sh")
    assert "uv run python scripts/guards/run_all.py" in _script_text("guard.sh")
```

- [ ] **Step 2: Run the script tests to verify they fail**

Run: `uv run pytest tests/unit/test_guard_scripts.py -q`
Expected: FAIL because the current scripts still probe `.venv/bin/python`, `python`, and `python3`, and `test.sh` and `guard.sh` do not run through uv yet.

- [ ] **Step 3: Rewrite `scripts/lint.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 127
fi

uv run python -m compileall src tests scripts
uv run python scripts/guards/python_compatibility.py
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts

if command -v node >/dev/null 2>&1; then
  while IFS= read -r js_file; do
    node --check "$js_file"
  done < <(find browser-cli-extension -type f -name '*.js' | sort)
  node --test browser-cli-extension/tests/popup_view.test.js
fi
```

- [ ] **Step 4: Rewrite `scripts/test.sh` and `scripts/guard.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 127
fi

uv run pytest -q
```

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 127
fi

uv run python scripts/guards/run_all.py
```

- [ ] **Step 5: Keep `scripts/check.sh` as the simple orchestrator**

```bash
#!/usr/bin/env bash
set -euo pipefail

./scripts/lint.sh
./scripts/test.sh
./scripts/guard.sh
```

- [ ] **Step 6: Run the script tests to verify they pass**

Run: `uv run pytest tests/unit/test_guard_scripts.py -q`
Expected: PASS

- [ ] **Step 7: Commit the script migration**

```bash
git add scripts/lint.sh scripts/test.sh scripts/guard.sh scripts/check.sh tests/unit/test_guard_scripts.py
git commit -m "chore: make repo scripts uv-only"
```

### Task 3: Migrate CI And Release Workflows To UV

**Files:**
- Create: `tests/unit/test_repo_workflows.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: Write failing workflow contract tests**

```python
from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _workflow_text(name: str) -> str:
    return (_repo_root() / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_ci_workflow_is_uv_only() -> None:
    workflow = _workflow_text("ci.yml")

    assert "astral-sh/setup-uv@" in workflow
    assert "uv sync --locked --dev" in workflow
    assert "uv run pytest tests/unit -v --tb=short" in workflow
    assert "uv run pytest tests/integration -v --tb=short -m \"not smoke\"" in workflow
    assert "python -m pip" not in workflow
    assert "pip install -e ." not in workflow
    assert "cache: 'pip'" not in workflow


def test_release_workflow_builds_and_publishes_with_uv() -> None:
    workflow = _workflow_text("release.yml")

    assert "astral-sh/setup-uv@" in workflow
    assert "uv build --no-sources" in workflow
    assert "uv publish" in workflow
    assert "pip install build twine" not in workflow
    assert "twine check" not in workflow
```

- [ ] **Step 2: Run the workflow tests to verify they fail**

Run: `uv run pytest tests/unit/test_repo_workflows.py -q`
Expected: FAIL because both workflows still install dependencies through pip and the release flow still uses build plus twine.

- [ ] **Step 3: Rewrite `.github/workflows/ci.yml` around uv**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  guard:
    name: Guard Checks
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

      - name: Run guards
        run: ./scripts/guard.sh

  unit-test:
    name: Unit Tests
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4

      - name: Set up uv and Python ${{ matrix.python-version }}
        uses: astral-sh/setup-uv@v7
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true

      - name: Sync dependencies
        run: uv sync --locked --dev

      - name: Run unit tests
        run: uv run pytest tests/unit -v --tb=short

  lint:
    name: Lint (Ruff)
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

      - name: Run Python compatibility guard
        run: uv run python scripts/guards/python_compatibility.py

      - name: Run Ruff linter
        run: uv run ruff check src tests scripts

      - name: Run Ruff formatter check
        run: uv run ruff format --check src tests scripts

  integration-test:
    name: Integration Tests
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

      - name: Install Playwright
        run: uv run playwright install --with-deps chromium

      - name: Run integration tests
        run: uv run pytest tests/integration -v --tb=short -m "not smoke"
        timeout-minutes: 15
```

- [ ] **Step 4: Rewrite `.github/workflows/release.yml` around uv**

```yaml
name: Release to PyPI

on:
  release:
    types: [created]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up uv
        uses: astral-sh/setup-uv@v7
        with:
          python-version-file: .python-version
          enable-cache: true

      - name: Build package
        run: uv build --no-sources

      - name: Publish to PyPI
        run: uv publish
```

- [ ] **Step 5: Run the workflow tests to verify they pass**

Run: `uv run pytest tests/unit/test_repo_workflows.py -q`
Expected: PASS

- [ ] **Step 6: Commit the workflow migration**

```bash
git add .github/workflows/ci.yml .github/workflows/release.yml tests/unit/test_repo_workflows.py
git commit -m "ci: migrate workflows to uv"
```

### Task 4: Rewrite README, Installed-User Docs, AGENTS, And Docs Guard Expectations

**Files:**
- Create: `docs/installed-with-uv.md`
- Modify: `README.md`
- Modify: `docs/installed-with-pip.md`
- Modify: `AGENTS.md`
- Modify: `scripts/guards/docs_sync.py`

- [ ] **Step 1: Tighten the docs-sync guard to the uv-first contract**

```python
REQUIRED_AGENT_PHRASES = [
    "Managed profile mode is the default browser backend.",
    "Extension mode is the preferred real-Chrome backend when the Browser CLI extension is connected and healthy.",
    "Driver rebinding may happen automatically only at safe idle points, and it must be reported as `state_reset` rather than treated as perfectly continuous state.",
    "`browser_cli.task_runtime` owns the public Python read contract and routes one-shot read through the daemon-managed browser lifecycle.",
    "Repository development is uv-only.",
    "`uv.lock`",
    "`.python-version`",
    "`scripts/guards/python_compatibility.py`",
    "`scripts/lint.sh`",
    "`scripts/test.sh`",
    "`scripts/guard.sh`",
    "`scripts/check.sh`",
]

REQUIRED_README_PHRASES = [
    "Python 3.10+",
    "uv sync --dev",
    "uv tool install browser-control-and-automation-cli",
    "uvx --from browser-control-and-automation-cli browser-cli",
    "browser-cli task validate",
    "browser-cli automation publish",
    "./scripts/lint.sh",
    "./scripts/test.sh",
    "./scripts/check.sh",
]
```

- [ ] **Step 2: Run the docs-sync guard test to verify it fails**

Run: `uv run pytest tests/unit/test_guard_scripts.py::test_docs_sync_guard_passes_for_current_repo -q`
Expected: FAIL because `README.md` and `AGENTS.md` still describe the repository as a mixed pip/uv setup and the installed-user guide still points at `docs/installed-with-pip.md`.

- [ ] **Step 3: Rewrite the README install and maintainer workflow sections**

```markdown
## Installation

Requirements:

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- Stable Google Chrome

### Install As A Tool

```bash
uv tool install browser-control-and-automation-cli
browser-cli doctor
browser-cli paths
browser-cli read https://example.com
```

### Run Without Installing

```bash
uvx --from browser-control-and-automation-cli browser-cli read https://example.com
```

### Install From Git

```bash
uv tool install git+https://github.com/hongv/browser-cli.git
browser-cli --help
```

## Development

```bash
git clone https://github.com/hongv/browser-cli.git
cd browser-cli
uv sync --dev
./scripts/lint.sh
./scripts/test.sh
./scripts/check.sh
```
```

- [ ] **Step 4: Add the new installed-user guide and demote the pip guide to migration-only status**

```markdown
# Installed With UV

This guide is for users who install Browser CLI as a tool with uv.

## Install

```bash
uv tool install browser-control-and-automation-cli
browser-cli doctor
browser-cli paths
```

## First Read

```bash
browser-cli read https://example.com
browser-cli read https://example.com --snapshot
browser-cli read https://example.com --scroll-bottom
```

## One-Off Execution

```bash
uvx --from browser-control-and-automation-cli browser-cli read https://example.com
```

## Install From Git

```bash
uv tool install git+https://github.com/hongv/browser-cli.git
browser-cli --help
```
```

```markdown
# Migrating From Pip To UV

Browser CLI now documents uv as the primary install path.

If you previously used pip, move to one of these flows:

```bash
uv tool install browser-control-and-automation-cli
browser-cli --help
```

or:

```bash
uvx --from browser-control-and-automation-cli browser-cli --help
```

The current installed-user guide lives at [`../../installed-with-uv.md`](../../installed-with-uv.md).
```

- [ ] **Step 5: Record the uv-only repository workflow in `AGENTS.md`**

```markdown
## System Snapshot

- Primary interface is CLI.
- Primary implementation language is Python.
- Repository development is uv-only.
- Repository dependency resolution is pinned through `uv.lock`.
- Repository local Python selection is pinned through `.python-version`.
```

```markdown
## Testing And Validation

- `scripts/lint.sh` owns repository lint execution.
- `scripts/test.sh` owns repository test execution.
- `scripts/guard.sh` owns architecture, product-contract, and doc-sync guards.
- `scripts/check.sh` runs lint, tests, and guard in the expected order.
- After each code change, run lint, tests, and guard.
- After each code change, run `uv sync --dev` when dependency metadata changes, then run `scripts/lint.sh`, `scripts/test.sh`, and `scripts/guard.sh`, or run `scripts/check.sh`.
```

- [ ] **Step 6: Run the docs-sync guard tests to verify they pass**

Run: `uv run pytest tests/unit/test_guard_scripts.py -q`
Expected: PASS

- [ ] **Step 7: Commit the documentation migration**

```bash
git add README.md docs/installed-with-uv.md docs/installed-with-pip.md AGENTS.md scripts/guards/docs_sync.py
git commit -m "docs: migrate project guidance to uv"
```

### Task 5: Replace Remaining PIP-Centric Install Hints And Re-Validate The Repo

**Files:**
- Create: `tests/unit/test_repo_text_contracts.py`
- Modify: `src/browser_cli/browser/session.py`
- Modify: `src/browser_cli/browser/service.py`
- Modify: `src/browser_cli/commands/doctor.py`

- [ ] **Step 1: Write the failing source-text contract tests**

```python
from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (_repo_root() / path).read_text(encoding="utf-8")


def test_browser_runtime_hints_point_maintainers_to_uv_sync() -> None:
    session_text = _read("src/browser_cli/browser/session.py")
    service_text = _read("src/browser_cli/browser/service.py")

    assert "python3 -m pip install -e ." not in session_text
    assert "python3 -m pip install -e ." not in service_text
    assert "uv sync --dev" in session_text
    assert "uv sync --dev" in service_text


def test_doctor_command_no_longer_describes_pip_users() -> None:
    doctor_text = _read("src/browser_cli/commands/doctor.py")

    assert '"""Install and runtime diagnostics for pip users."""' not in doctor_text
    assert "uv tool install browser-control-and-automation-cli" in doctor_text or "uv sync --dev" in doctor_text
```

- [ ] **Step 2: Run the source-text contract tests to verify they fail**

Run: `uv run pytest tests/unit/test_repo_text_contracts.py -q`
Expected: FAIL because `session.py`, `service.py`, and `doctor.py` still contain pip-centric text.

- [ ] **Step 3: Replace the remaining pip-centric hints**

```python
raise BrowserUnavailableError(
    "Playwright is not installed in this repo environment. Run: uv sync --dev"
) from exc
```

```python
"""Install and runtime diagnostics for Browser CLI environments."""
```

```python
return DoctorCheck(
    id="playwright",
    status="fail",
    summary="Playwright Python package is not installed.",
    next="run uv sync --dev in the repository checkout, then re-run browser-cli doctor",
)
```

- [ ] **Step 4: Run the new source-text tests and the full repository validation**

Run: `uv run pytest tests/unit/test_repo_text_contracts.py -q`
Expected: PASS

Run: `./scripts/check.sh`
Expected: PASS

Run: `uv build --no-sources`
Expected: PASS and build artifacts appear under `dist/`.

- [ ] **Step 5: Commit the final uv migration cleanup**

```bash
git add src/browser_cli/browser/session.py src/browser_cli/browser/service.py src/browser_cli/commands/doctor.py tests/unit/test_repo_text_contracts.py
git commit -m "chore: finish uv migration"
```

## Self-Review

### Spec coverage

- uv-only repository metadata is covered by Task 1.
- uv-only scripts are covered by Task 2.
- uv-only CI and release are covered by Task 3.
- uv-first user and maintainer docs plus AGENTS updates are covered by Task 4.
- remaining install and recovery hints plus final validation are covered by Task 5.

No approved spec requirement is left without a task.

### Placeholder scan

- No placeholder markers or deferred implementation language remain.
- Every task includes exact file paths.
- Every code-changing step includes concrete code or full file contents.
- Every verification step includes an exact command and expected result.

### Type and naming consistency

- The plan consistently uses `dependency-groups.dev`, `.python-version`, and `uv.lock`.
- The scripts consistently use the same uv failure message and `uv run` execution model.
- The docs consistently distinguish repository maintainers (`uv sync --dev`) from installed users (`uv tool install` and `uvx`).
