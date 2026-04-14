# Browser CLI Uninstall Doc Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a maintainer-oriented uninstall guide for Browser CLI that documents full cleanup of the repository development environment and Browser CLI home, with backup guidance and links from the main install docs.

**Architecture:** Add a new `docs/uninstall.md` document built around the current runtime path model and cleanup commands, then link to it from `README.md` and `docs/installed-with-uv.md`. Lock the new documentation surface with a repo text-contract test so the uninstall guide and its entry points do not silently disappear later.

**Tech Stack:** Markdown docs, pytest repo text-contract tests, Browser CLI path and lifecycle commands

---

## File Map

- Create: `docs/uninstall.md`
  Responsibility: full uninstall guide for maintainers and developers, including backup, runtime cleanup, repo cleanup, Browser CLI home deletion, optional uv tool uninstall, and verification.
- Modify: `README.md`
  Responsibility: expose the uninstall guide from the main docs surface.
- Modify: `docs/installed-with-uv.md`
  Responsibility: point installed users at the uninstall guide.
- Modify: `tests/unit/test_repo_text_contracts.py`
  Responsibility: lock the presence of the uninstall guide and its documentation entry points.
- Modify: `docs/superpowers/plans/2026-04-14-browser-cli-uninstall-doc-implementation-plan.md`
  Responsibility: update checkbox state during execution if this plan is used as the working log.

## Task 1: Lock The Uninstall Documentation Surface With A Repo Text Contract

**Files:**
- Modify: `tests/unit/test_repo_text_contracts.py`
- Test: `tests/unit/test_repo_text_contracts.py`

- [x] **Step 1: Add the failing uninstall documentation test**

Append to `tests/unit/test_repo_text_contracts.py`:

```python
def test_uninstall_doc_is_linked_from_primary_install_docs() -> None:
    uninstall_text = _read("docs/uninstall.md")
    readme_text = _read("README.md")
    uv_doc_text = _read("docs/installed-with-uv.md")

    assert "# Uninstall Browser CLI" in uninstall_text
    assert "browser-cli paths" in uninstall_text
    assert "browser-cli automation stop" in uninstall_text
    assert "browser-cli reload" in uninstall_text
    assert "uv tool uninstall browser-cli" in uninstall_text
    assert "docs/uninstall.md" in readme_text
    assert "docs/uninstall.md" in uv_doc_text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_repo_text_contracts.py::test_uninstall_doc_is_linked_from_primary_install_docs -v
```

Expected: FAIL because `docs/uninstall.md` does not exist and the existing docs do not link to it.

- [x] **Step 3: Add the minimal uninstall document and link placeholders**

Create `docs/uninstall.md`:

```markdown
# Uninstall Browser CLI
```

Add a docs link in `README.md`:

```markdown
- Uninstall and cleanup guidance: [`docs/uninstall.md`](docs/uninstall.md)
```

Add a pointer in `docs/installed-with-uv.md`:

```markdown
To remove Browser CLI later, see [`docs/uninstall.md`](docs/uninstall.md).
```

- [ ] **Step 4: Run the test to verify it still fails for missing content**

Run:

```bash
uv run pytest tests/unit/test_repo_text_contracts.py::test_uninstall_doc_is_linked_from_primary_install_docs -v
```

Expected: FAIL because the uninstall doc stub does not yet contain the required commands and headings.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_repo_text_contracts.py docs/uninstall.md README.md docs/installed-with-uv.md
git commit -m "test: lock uninstall documentation surface"
```

## Task 2: Write The Full Uninstall Guide

**Files:**
- Modify: `docs/uninstall.md`
- Test: `tests/unit/test_repo_text_contracts.py`

- [x] **Step 1: Replace the stub with the full uninstall document**

Write `docs/uninstall.md`:

```markdown
# Uninstall Browser CLI

This guide is for repository maintainers and local developers who want to fully
remove Browser CLI from a machine. It covers:

- stopping Browser CLI runtime processes
- backing up high-value local data first
- removing the repository development environment
- removing Browser CLI home data
- optionally removing any uv tool installation

## Before You Delete Anything

Inspect the current Browser CLI runtime paths and status first:

```bash
browser-cli paths
browser-cli status
```

If you set `BROWSER_CLI_HOME`, Browser CLI home may not be `~/.browser-cli`.
Use the `home` path shown by `browser-cli paths` as the deletion target.

## Back Up What You Want To Keep

Before deleting Browser CLI home, consider backing up these paths from
`browser-cli paths`:

- `tasks_dir`
- `automations_dir`
- `automation_db_path`
- optionally `artifacts_dir`

Deleting Browser CLI home removes local task source, published automation
snapshots, automation persistence, runtime logs, and artifacts.

## Stop Runtime Processes

Stop the automation service and clear daemon runtime state before deleting files:

```bash
browser-cli automation stop
browser-cli reload
```

`browser-cli reload` is runtime cleanup, not uninstall. It resets Browser CLI
state before deletion, but it does not remove Browser CLI files by itself.

## Remove The Repository Development Environment

From the repository root, remove the local development environment:

```bash
rm -rf .venv
rm -rf .pytest_cache
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
```

This step only removes repo-local development state. It does not remove Browser
CLI home data.

## Remove Browser CLI Home Data

Delete the Browser CLI home reported by `browser-cli paths`. The default path is
usually:

```bash
rm -rf ~/.browser-cli
```

If `browser-cli paths` showed a different `home`, delete that path instead.

Removing Browser CLI home deletes:

- `run/` runtime state and logs
- `artifacts/`
- `tasks/`
- `automations/`
- `automations.db`
- managed-profile runtime state stored under Browser CLI home

## Optional: Remove uv Tool Installation

If you also installed Browser CLI as a uv tool, remove it separately:

```bash
uv tool uninstall browser-cli
```

This does not remove:

- the repository checkout
- Browser CLI home data

## Verify Removal

Verify repo-local cleanup:

```bash
test ! -d .venv && echo "repo venv removed"
```

Verify Browser CLI home removal by checking the path you identified earlier:

```bash
test ! -d ~/.browser-cli && echo "browser-cli home removed"
```

If you used a custom `BROWSER_CLI_HOME`, replace `~/.browser-cli` with the
actual `home` path shown by `browser-cli paths`.
```

- [x] **Step 2: Run the focused repo text-contract test**

Run:

```bash
uv run pytest tests/unit/test_repo_text_contracts.py::test_uninstall_doc_is_linked_from_primary_install_docs -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add docs/uninstall.md
git commit -m "docs: add browser-cli uninstall guide"
```

## Task 3: Link The Guide From The Main Install Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/installed-with-uv.md`
- Test: `tests/unit/test_repo_text_contracts.py`

- [x] **Step 1: Add the uninstall guide link to README documentation**

Update the Documentation section in `README.md`:

```markdown
## Documentation

- Repo navigation and subsystem ownership: [`AGENTS.md`](AGENTS.md)
- Installed-user guide: [`docs/installed-with-uv.md`](docs/installed-with-uv.md)
- Uninstall and cleanup guide: [`docs/uninstall.md`](docs/uninstall.md)
```

- [x] **Step 2: Add the uninstall pointer to the uv install guide**

Append to `docs/installed-with-uv.md`:

```markdown
## Remove Browser CLI

To remove Browser CLI later, including Browser CLI home data and local cleanup
steps for maintainers, see [`docs/uninstall.md`](docs/uninstall.md).
```

- [x] **Step 3: Run the focused repo text-contract test again**

Run:

```bash
uv run pytest tests/unit/test_repo_text_contracts.py::test_uninstall_doc_is_linked_from_primary_install_docs -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add README.md docs/installed-with-uv.md tests/unit/test_repo_text_contracts.py
git commit -m "docs: link browser-cli uninstall guide"
```

## Task 4: Run Full Validation And Record The Final State

**Files:**
- Modify: `docs/superpowers/plans/2026-04-14-browser-cli-uninstall-doc-implementation-plan.md`
- Test: `tests/unit/test_repo_text_contracts.py`

- [x] **Step 1: Run the relevant unit tests**

Run:

```bash
uv run pytest tests/unit/test_repo_text_contracts.py -v
```

Expected: PASS

- [x] **Step 2: Run repository lint**

Run:

```bash
scripts/lint.sh
```

Expected: exit code 0

- [x] **Step 3: Run repository tests**

Run:

```bash
scripts/test.sh
```

Expected: exit code 0

- [x] **Step 4: Run repository guards**

Run:

```bash
scripts/guard.sh
```

Expected: exit code 0

- [ ] **Step 5: Commit the completed uninstall documentation change**

```bash
git add docs/uninstall.md README.md docs/installed-with-uv.md tests/unit/test_repo_text_contracts.py docs/superpowers/plans/2026-04-14-browser-cli-uninstall-doc-implementation-plan.md
git commit -m "docs: document browser-cli uninstall"
```

## Self-Review

- Spec coverage:
  - full maintainer-oriented uninstall guidance is covered in Task 2
  - backup guidance and runtime cleanup commands are covered in Task 2
  - README and installed-user doc links are covered in Task 3
  - repo-level regression protection is covered in Task 1
- Placeholder scan:
  - no deferred implementation markers remain
  - all file paths and commands are explicit
- Type and contract consistency:
  - the uninstall guide uses only commands that exist today
  - the docs point to `docs/uninstall.md`
  - the guide distinguishes repo cleanup, Browser CLI home deletion, and uv tool uninstall
