# Browser CLI Delivery Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single delivery-oriented skill with a three-skill Browser CLI delivery stack that captures exploration feedback into `task.meta.json`, converges validated paths into `task.py`, and keeps `automation.toml` plus publish optional.

**Architecture:** Add three new skills under `skills/` with clear role boundaries: `browser-cli-delivery` as the orchestrator, `browser-cli-explore` as the metadata-first exploration skill, and `browser-cli-converge` as the task-code convergence skill. Lock the new topology with repo text-contract tests, update `AGENTS.md` to point maintainers at the new entrypoint, and keep `skills/browser-cli-explore-delivery/SKILL.md` as a compatibility wrapper instead of the primary workflow definition.

**Tech Stack:** Markdown skill docs, pytest repo text-contract tests, AGENTS.md repository guidance, Browser CLI task and automation contracts

---

## File Map

- Create: `skills/browser-cli-delivery/SKILL.md`
  Responsibility: user-facing orchestration rules, stage model, rollback rules, optional `automation.toml` and publish branch.
- Create: `skills/browser-cli-explore/SKILL.md`
  Responsibility: Browser CLI exploration rules, task-mode selection, durable feedback capture into `task.meta.json`.
- Create: `skills/browser-cli-converge/SKILL.md`
  Responsibility: convergence rules for `task.py`, `Flow` usage, metadata-code alignment, task validation.
- Create: `tests/unit/test_repo_skill_docs.py`
  Responsibility: lock the new skill topology and the required contract text so future edits do not drift back to the old single-skill model.
- Modify: `skills/browser-cli-explore-delivery/SKILL.md`
  Responsibility: compatibility wrapper that redirects callers to `browser-cli-delivery` while preserving migration context.
- Modify: `AGENTS.md`
  Responsibility: point Browser CLI maintainers to the new top-level skill instead of the old one.
- Modify: `docs/superpowers/plans/2026-04-14-browser-cli-delivery-skills-implementation-plan.md`
  Responsibility: update checkbox state during execution if you are using this plan as the working log.

## Task 1: Lock The New Skill Topology With A Repo Text Contract

**Files:**
- Create: `tests/unit/test_repo_skill_docs.py`
- Test: `tests/unit/test_repo_skill_docs.py`

- [ ] **Step 1: Write the failing topology test**

```python
from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (_repo_root() / path).read_text(encoding="utf-8")


def test_browser_cli_skill_topology_exists() -> None:
    root = _repo_root()

    assert (root / "skills" / "browser-cli-delivery" / "SKILL.md").exists()
    assert (root / "skills" / "browser-cli-explore" / "SKILL.md").exists()
    assert (root / "skills" / "browser-cli-converge" / "SKILL.md").exists()


def test_agents_points_to_browser_cli_delivery_skill() -> None:
    agents_text = _read("AGENTS.md")

    assert "skills/browser-cli-delivery/SKILL.md" in agents_text
    assert "skills/browser-cli-explore-delivery/SKILL.md" not in agents_text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/unit/test_repo_skill_docs.py::test_browser_cli_skill_topology_exists -v
```

Expected: FAIL because the new skill directories do not exist yet.

- [ ] **Step 3: Add the minimal files and AGENTS pointer needed to make the topology real**

Create `skills/browser-cli-delivery/SKILL.md`:

```markdown
---
name: browser-cli-delivery
description: Orchestrate Browser CLI exploration, convergence, validation, and optional automation packaging for reusable web tasks.
---

# Browser CLI Delivery
```

Create `skills/browser-cli-explore/SKILL.md`:

```markdown
---
name: browser-cli-explore
description: Explore real websites with Browser CLI, validate task mode, and distill durable feedback into task metadata.
---

# Browser CLI Explore
```

Create `skills/browser-cli-converge/SKILL.md`:

```markdown
---
name: browser-cli-converge
description: Turn validated Browser CLI exploration into stable task.py execution logic and task validation.
---

# Browser CLI Converge
```

Update the Browser-CLI-specific guidance line in `AGENTS.md`:

```markdown
- Browser-CLI-specific agent delivery guidance:
  `skills/browser-cli-delivery/SKILL.md`
```

- [ ] **Step 4: Run the test to verify the topology passes**

Run:

```bash
pytest tests/unit/test_repo_skill_docs.py::test_browser_cli_skill_topology_exists tests/unit/test_repo_skill_docs.py::test_agents_points_to_browser_cli_delivery_skill -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_repo_skill_docs.py skills/browser-cli-delivery/SKILL.md skills/browser-cli-explore/SKILL.md skills/browser-cli-converge/SKILL.md AGENTS.md
git commit -m "test: lock browser-cli delivery skill topology"
```

## Task 2: Implement The Metadata-First Exploration Skill

**Files:**
- Modify: `skills/browser-cli-explore/SKILL.md`
- Modify: `tests/unit/test_repo_skill_docs.py`
- Test: `tests/unit/test_repo_skill_docs.py`

- [ ] **Step 1: Extend the repo text-contract test for exploration requirements**

Append to `tests/unit/test_repo_skill_docs.py`:

```python
def test_browser_cli_explore_skill_records_feedback_into_task_metadata() -> None:
    skill_text = _read("skills/browser-cli-explore/SKILL.md")

    assert "task.meta.json" in skill_text
    assert "browser-cli is the primary browser execution path" in skill_text
    assert "environment" in skill_text
    assert "success_path" in skill_text
    assert "recovery_hints" in skill_text
    assert "failures" in skill_text
    assert "knowledge" in skill_text
    assert "Do not record raw logs" in skill_text
```

- [ ] **Step 2: Run the exploration contract test to verify it fails**

Run:

```bash
pytest tests/unit/test_repo_skill_docs.py::test_browser_cli_explore_skill_records_feedback_into_task_metadata -v
```

Expected: FAIL because the file only contains the stub header.

- [ ] **Step 3: Replace the stub header with the full exploration skill**

Write `skills/browser-cli-explore/SKILL.md`:

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

## When to Use

Use this skill when:

- a web task still needs exploration or validation
- the page depends on real browser state, cookies, login, or rendering
- the next useful artifact is better task metadata, not yet final `task.py`

Do not use this skill when:

- the success path is already validated end to end
- the work is only task-code refactoring with no evidence gap
- the task is pure API work with no Browser CLI dependency

## Hard Rules

- browser-cli is the primary browser execution path
- choose the task mode before broad exploration
- capture only observations that change the next decision
- update `task.meta.json` as a rolling feedback sink
- treat these metadata sections as required destinations for durable knowledge:
  `environment`, `success_path`, `recovery_hints`, `failures`, `knowledge`
- stop once the evidence is strong enough for deterministic implementation
- Do not record raw logs, chat transcripts, or exploratory dead ends in metadata
- Do not turn one lucky run into stable knowledge without a verification step

## Phase Order

1. Confirm the site-specific preflight assumptions:
   login state, cookies, locale, browser profile, writable artifacts, Python env
2. Choose the task mode:
   `ref-driven`, `content-first`, `lazy-scroll`, `login-state-first`, or
   `browser-state/network-assisted`
3. Explore with the smallest reliable Browser CLI signal
4. Capture durable findings into `task.meta.json`
5. Stop when the success path, waits, refs, and failure lessons are clear enough
   for `task.py`

## Metadata Capture Rules

- `environment`: site, entry URL, login requirements, profile assumptions,
  browser assumptions
- `success_path`: validated steps, key refs, assertions, artifacts
- `recovery_hints`: retryable steps, alternate paths, stale-ref strategy, wait
  points, anti-bot recovery
- `failures`: repeatable failure modes and the lesson each one teaches
- `knowledge`: stable selectors/roles, semantic-ref notes, pagination,
  lazy-load, anti-bot, and output interpretation rules

## Done Criteria

This skill is complete when:

- the task mode is known
- the stable path is understood
- the fragile points are documented
- `task.meta.json` contains enough evidence for `browser-cli-converge`

## Common Mistakes

- exploring with direct Playwright instead of Browser CLI
- jumping straight from browsing to `task.py`
- keeping the useful lessons only in chat
- recording logs instead of reusable metadata
```

- [ ] **Step 4: Run the exploration contract test to verify it passes**

Run:

```bash
pytest tests/unit/test_repo_skill_docs.py::test_browser_cli_explore_skill_records_feedback_into_task_metadata -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_repo_skill_docs.py skills/browser-cli-explore/SKILL.md
git commit -m "docs: add browser-cli explore skill"
```

## Task 3: Implement The Task-Code Convergence Skill

**Files:**
- Modify: `skills/browser-cli-converge/SKILL.md`
- Modify: `tests/unit/test_repo_skill_docs.py`
- Test: `tests/unit/test_repo_skill_docs.py`

- [ ] **Step 1: Extend the repo text-contract test for convergence requirements**

Append to `tests/unit/test_repo_skill_docs.py`:

```python
def test_browser_cli_converge_skill_centers_task_py_and_flow_validation() -> None:
    skill_text = _read("skills/browser-cli-converge/SKILL.md")

    assert "task.py is the single source of execution logic" in skill_text
    assert "browser_cli.task_runtime.Flow" in skill_text
    assert "browser-cli task validate" in skill_text
    assert "browser-cli task run" in skill_text
    assert "must stay aligned with task.meta.json" in skill_text
```

- [ ] **Step 2: Run the convergence contract test to verify it fails**

Run:

```bash
pytest tests/unit/test_repo_skill_docs.py::test_browser_cli_converge_skill_centers_task_py_and_flow_validation -v
```

Expected: FAIL because the file only contains the stub header.

- [ ] **Step 3: Replace the stub header with the full convergence skill**

Write `skills/browser-cli-converge/SKILL.md`:

```markdown
---
name: browser-cli-converge
description: Turn validated Browser CLI exploration into stable task.py execution logic and task validation.
---

# Browser CLI Converge

## Overview

Use this skill after exploration has already validated the success path.
Its job is to encode that evidence into stable `task.py` logic and keep the
implementation aligned with `task.meta.json`.

## When to Use

Use this skill when:

- the success path is already validated
- the task now needs executable Browser CLI task code
- waits, assertions, and artifacts are known well enough to encode

Do not use this skill when:

- the site still has unresolved evidence gaps
- the task mode is still unclear
- validation failures show the metadata is incomplete

## Hard Rules

- task.py is the single source of execution logic
- browser interactions must go through `browser_cli.task_runtime.Flow`
- task code must stay aligned with task.meta.json
- keep exploration-only retries, branches, and debug logic out of the final task
- validate with `browser-cli task validate`
- use `browser-cli task run` when runtime proof is needed
- if validation exposes an evidence gap, go back to `browser-cli-explore`

## Phase Order

1. Read the validated `task.meta.json`
2. Encode the stable success path in `task.py`
3. Add explicit waits, assertions, and artifact writes
4. Verify metadata-code alignment
5. Run `browser-cli task validate`
6. Run `browser-cli task run` if the task shape requires live proof
7. If evidence is missing, return to exploration instead of guessing

## Done Criteria

This skill is complete when:

- `task.py` replays the validated path
- waits and assertions are explicit
- the code and metadata describe the same workflow
- task validation passes

## Common Mistakes

- bypassing the task runtime with direct Playwright
- encoding guesses instead of validated waits or refs
- letting metadata and code drift apart
- patching around a missing exploration lesson instead of going back
```

- [ ] **Step 4: Run the convergence contract test to verify it passes**

Run:

```bash
pytest tests/unit/test_repo_skill_docs.py::test_browser_cli_converge_skill_centers_task_py_and_flow_validation -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_repo_skill_docs.py skills/browser-cli-converge/SKILL.md
git commit -m "docs: add browser-cli converge skill"
```

## Task 4: Implement The Orchestrator Skill And Rollback Rules

**Files:**
- Modify: `skills/browser-cli-delivery/SKILL.md`
- Modify: `tests/unit/test_repo_skill_docs.py`
- Test: `tests/unit/test_repo_skill_docs.py`

- [ ] **Step 1: Extend the repo text-contract test for orchestration requirements**

Append to `tests/unit/test_repo_skill_docs.py`:

```python
def test_browser_cli_delivery_skill_orchestrates_explore_converge_and_optional_automation() -> None:
    skill_text = _read("skills/browser-cli-delivery/SKILL.md")

    assert "browser-cli-explore" in skill_text
    assert "browser-cli-converge" in skill_text
    assert "task.py + task.meta.json" in skill_text
    assert "automation.toml" in skill_text
    assert "publish" in skill_text
    assert "If validation fails because evidence is missing, go back to explore" in skill_text
```

- [ ] **Step 2: Run the orchestration contract test to verify it fails**

Run:

```bash
pytest tests/unit/test_repo_skill_docs.py::test_browser_cli_delivery_skill_orchestrates_explore_converge_and_optional_automation -v
```

Expected: FAIL because the file only contains the stub header.

- [ ] **Step 3: Replace the stub header with the full orchestration skill**

Write `skills/browser-cli-delivery/SKILL.md`:

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

## When to Use

Use this skill when:

- the user wants a reusable browser task
- the work may require exploration, iteration, and validation
- the final deliverable should match Browser CLI task artifacts

Do not use this skill when:

- one-off browsing is enough
- the task is not Browser CLI based
- the work is already scoped to only one lower-level skill

## Hard Rules

- this is the main user-facing skill
- call `browser-cli-explore` when evidence is missing
- call `browser-cli-converge` when the success path is validated
- default completion is `task.py + task.meta.json`
- `automation.toml` and publish are optional and require user choice
- If validation fails because evidence is missing, go back to explore
- do not publish by default

## Phase Order

1. Preflight: confirm Browser CLI, Python environment, login/profile, and site assumptions
2. Explore: call `browser-cli-explore` to validate the task mode and capture feedback
3. Converge: call `browser-cli-converge` to encode the stable path in `task.py`
4. Validate: run task validation and decide whether to fix code or return to explore
5. Optional automation: ask whether to create `automation.toml`
6. Optional publish: ask whether to run Browser CLI automation publish

## Done Criteria

This skill is complete when:

- `task.py + task.meta.json` are stable
- validation passed
- optional automation work is either completed or intentionally skipped by the user

## Common Mistakes

- skipping metadata capture
- converging before the success path is real
- generating automation packaging too early
- treating one successful page run as enough evidence
```

- [ ] **Step 4: Run the orchestration contract test to verify it passes**

Run:

```bash
pytest tests/unit/test_repo_skill_docs.py::test_browser_cli_delivery_skill_orchestrates_explore_converge_and_optional_automation -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_repo_skill_docs.py skills/browser-cli-delivery/SKILL.md
git commit -m "docs: add browser-cli delivery skill"
```

## Task 5: Convert The Legacy Skill Into A Compatibility Wrapper

**Files:**
- Modify: `skills/browser-cli-explore-delivery/SKILL.md`
- Modify: `tests/unit/test_repo_skill_docs.py`
- Test: `tests/unit/test_repo_skill_docs.py`

- [ ] **Step 1: Extend the repo text-contract test for legacy redirection**

Append to `tests/unit/test_repo_skill_docs.py`:

```python
def test_legacy_browser_cli_explore_delivery_skill_redirects_to_new_entrypoint() -> None:
    skill_text = _read("skills/browser-cli-explore-delivery/SKILL.md")

    assert "Compatibility wrapper" in skill_text
    assert "browser-cli-delivery" in skill_text
    assert "browser-cli-explore" in skill_text
    assert "browser-cli-converge" in skill_text
```

- [ ] **Step 2: Run the legacy wrapper test to verify it fails**

Run:

```bash
pytest tests/unit/test_repo_skill_docs.py::test_legacy_browser_cli_explore_delivery_skill_redirects_to_new_entrypoint -v
```

Expected: FAIL because the legacy skill still contains the old single-skill workflow.

- [ ] **Step 3: Replace the old body with a compact compatibility wrapper**

Write `skills/browser-cli-explore-delivery/SKILL.md`:

```markdown
---
name: browser-cli-explore-delivery
description: Compatibility wrapper for the newer Browser CLI delivery skill stack.
---

# Browser CLI Explore Delivery

Compatibility wrapper.

Use `browser-cli-delivery` as the main entrypoint for Browser CLI task delivery.

- `browser-cli-explore` owns Browser CLI exploration and feedback capture into
  `task.meta.json`
- `browser-cli-converge` owns convergence into `task.py`
- `browser-cli-delivery` owns stage transitions, validation rollback, optional
  `automation.toml`, and optional publish

Do not extend this wrapper with new primary workflow logic. Put new delivery
guidance in the three new skills.
```

- [ ] **Step 4: Run the legacy wrapper test to verify it passes**

Run:

```bash
pytest tests/unit/test_repo_skill_docs.py::test_legacy_browser_cli_explore_delivery_skill_redirects_to_new_entrypoint -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_repo_skill_docs.py skills/browser-cli-explore-delivery/SKILL.md
git commit -m "docs: redirect legacy browser-cli delivery skill"
```

## Task 6: Run Full Validation And Record The Final State

**Files:**
- Modify: `docs/superpowers/plans/2026-04-14-browser-cli-delivery-skills-implementation-plan.md`
- Test: `tests/unit/test_repo_skill_docs.py`

- [ ] **Step 1: Run the focused unit test file**

Run:

```bash
pytest tests/unit/test_repo_skill_docs.py -v
```

Expected: PASS

- [ ] **Step 2: Run repository lint**

Run:

```bash
scripts/lint.sh
```

Expected: exit code 0

- [ ] **Step 3: Run repository tests**

Run:

```bash
scripts/test.sh
```

Expected: exit code 0

- [ ] **Step 4: Run repository guards**

Run:

```bash
scripts/guard.sh
```

Expected: exit code 0

- [ ] **Step 5: Commit the completed delivery-skill migration**

```bash
git add skills/browser-cli-delivery/SKILL.md skills/browser-cli-explore/SKILL.md skills/browser-cli-converge/SKILL.md skills/browser-cli-explore-delivery/SKILL.md AGENTS.md tests/unit/test_repo_skill_docs.py docs/superpowers/plans/2026-04-14-browser-cli-delivery-skills-implementation-plan.md
git commit -m "docs: add browser-cli delivery skill stack"
```

## Self-Review

- Spec coverage:
  - three-skill topology is covered in Tasks 1, 4, and 5
  - metadata-first exploration is covered in Task 2
  - `task.py` convergence and validation rules are covered in Task 3
  - optional `automation.toml` and publish are covered in Task 4
  - maintainer navigation update is covered in Task 1
- Placeholder scan:
  - no deferred implementation markers remain
  - every file path and command is explicit
- Type and contract consistency:
  - all tests reference the final short names
  - all skill docs use `task.meta.json`, `task.py`, and `automation.toml`
  - AGENTS points to `skills/browser-cli-delivery/SKILL.md`
