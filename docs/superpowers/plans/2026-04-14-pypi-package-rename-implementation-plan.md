# Browser CLI PyPI Package Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the published Browser CLI distribution from `browserctl` to `browser-control-and-automation-cli` without changing the `browser-cli` executable or `browser_cli` import path.

**Architecture:** Treat this as a packaging-contract change, not a product-surface rename. Update the distribution name in project metadata, then propagate the same exact install string through scripts, docs, user hints, and repo guards so validation runs against one consistent published-name contract.

**Tech Stack:** `pyproject.toml`, `uv.lock`, shell scripts, Markdown docs, pytest repo text-contract tests, uv packaging workflow

---

## File Map

- Create: `docs/superpowers/specs/2026-04-14-pypi-package-rename-design.md`
  Responsibility: durable reasoning for why only the published package name changes.
- Create: `docs/superpowers/plans/2026-04-14-pypi-package-rename-implementation-plan.md`
  Responsibility: execution handoff and audit trail for the rename.
- Modify: `pyproject.toml`
  Responsibility: publish the new distribution name.
- Modify: `README.md`
  Responsibility: primary install and `uvx` examples use the new distribution name.
- Modify: `docs/installed-with-uv.md`
  Responsibility: installed-user guide uses the new distribution name.
- Modify: `docs/installed-with-pip.md`
  Responsibility: pip-to-uv migration examples use the new distribution name.
- Modify: `docs/uninstall.md`
  Responsibility: uninstall guidance removes the new distribution name.
- Modify: `src/browser_cli/commands/doctor.py`
  Responsibility: repair reinstall hints shown to users when package or Playwright checks fail.
- Modify: `scripts/test.sh`
  Responsibility: reinstall the renamed editable package before pytest.
- Modify: `scripts/guards/docs_sync.py`
  Responsibility: lock README install examples to the renamed distribution.
- Modify: `tests/unit/test_guard_scripts.py`
  Responsibility: assert the test script refreshes the renamed package.
- Modify: `tests/unit/test_repo_text_contracts.py`
  Responsibility: assert repo text surfaces describe the renamed distribution.
- Modify: `AGENTS.md`
  Responsibility: preserve durable package-name guidance for future agents.
- Modify: `uv.lock`
  Responsibility: keep the root lock entry aligned with the renamed project metadata.

### Task 1: Rename The Published Distribution Contract

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `scripts/test.sh`

- [ ] **Step 1: Write the failing metadata expectation**

```python
from pathlib import Path


def test_project_name_is_long_unique_distribution() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "browser-control-and-automation-cli"' in text
```

- [ ] **Step 2: Run a targeted check to verify the old name is still present**

Run:

```bash
rg -n 'name = "browserctl"|name = "browser-control-and-automation-cli"' pyproject.toml uv.lock
```

Expected: `pyproject.toml` and `uv.lock` still show `browserctl`.

- [ ] **Step 3: Update the package metadata and lock entry**

```toml
[project]
name = "browser-control-and-automation-cli"
```

Run:

```bash
uv lock
```

Expected: the root `[[package]]` entry in `uv.lock` changes from `browserctl`
to `browser-control-and-automation-cli`.

- [ ] **Step 4: Refresh the editable environment with the renamed package**

Run:

```bash
uv sync --dev --reinstall-package browser-control-and-automation-cli
```

Expected: the environment sync completes without package-name mismatch errors.

### Task 2: Update User-Facing Install, Reinstall, And Uninstall Surfaces

**Files:**
- Modify: `README.md`
- Modify: `docs/installed-with-uv.md`
- Modify: `docs/installed-with-pip.md`
- Modify: `docs/uninstall.md`
- Modify: `src/browser_cli/commands/doctor.py`
- Modify: `AGENTS.md`
- Test: `tests/unit/test_repo_text_contracts.py`

- [ ] **Step 1: Write the failing text-contract expectations**

```python
def test_uninstall_doc_uses_new_distribution_name() -> None:
    uninstall_text = _read("docs/uninstall.md")
    assert "uv tool uninstall browser-control-and-automation-cli" in uninstall_text
```

- [ ] **Step 2: Run the targeted repo text test to verify it fails before edits**

Run:

```bash
pytest tests/unit/test_repo_text_contracts.py::test_uninstall_doc_is_linked_from_primary_install_docs -v
```

Expected: FAIL while the docs still mention `browserctl`.

- [ ] **Step 3: Replace every install-facing `browserctl` reference with the new distribution name**

```text
uv tool install browser-control-and-automation-cli
uvx --from browser-control-and-automation-cli browser-cli ...
uv tool uninstall browser-control-and-automation-cli
uv sync --dev --reinstall-package browser-control-and-automation-cli
```

Also update the doctor hints so user recovery guidance matches the new package
name exactly.

- [ ] **Step 4: Run the targeted repo text tests**

Run:

```bash
pytest tests/unit/test_repo_text_contracts.py -q
```

Expected: PASS

### Task 3: Update Guards And Script-Level Contract Coverage

**Files:**
- Modify: `scripts/test.sh`
- Modify: `scripts/guards/docs_sync.py`
- Modify: `tests/unit/test_guard_scripts.py`
- Test: `tests/unit/test_guard_scripts.py`

- [ ] **Step 1: Write the failing script-contract expectation**

```python
def test_test_script_reinstalls_new_distribution_name() -> None:
    test_script = (repo_root() / "scripts" / "test.sh").read_text(encoding="utf-8")
    assert "browser-control-and-automation-cli" in test_script
```

- [ ] **Step 2: Run the targeted script-contract test to verify it fails first**

Run:

```bash
pytest tests/unit/test_guard_scripts.py::test_test_and_guard_scripts_execute_through_uv -v
```

Expected: FAIL because `scripts/test.sh` still reinstalls `browserctl`.

- [ ] **Step 3: Update the script and guard contract strings**

```bash
uv sync --dev --reinstall-package browser-control-and-automation-cli
```

```python
REQUIRED_README_PHRASES = [
    "uv tool install browser-control-and-automation-cli",
    "uvx --from browser-control-and-automation-cli browser-cli",
]
```

- [ ] **Step 4: Run the targeted guard-script tests**

Run:

```bash
pytest tests/unit/test_guard_scripts.py -q
```

Expected: PASS

### Task 4: Full Validation

**Files:**
- Modify: `uv.lock`
- Test: `scripts/lint.sh`
- Test: `scripts/test.sh`
- Test: `scripts/guard.sh`

- [ ] **Step 1: Refresh the lock and environment**

Run:

```bash
uv lock
uv sync --dev --reinstall-package browser-control-and-automation-cli
```

Expected: lockfile and editable install both reference the renamed distribution.

- [ ] **Step 2: Run lint**

Run:

```bash
./scripts/lint.sh
```

Expected: PASS

- [ ] **Step 3: Run tests**

Run:

```bash
./scripts/test.sh
```

Expected: PASS

- [ ] **Step 4: Run guards**

Run:

```bash
./scripts/guard.sh
```

Expected: PASS
