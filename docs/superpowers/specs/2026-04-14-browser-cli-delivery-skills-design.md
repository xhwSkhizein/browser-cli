# Browser CLI Delivery Skills Design

Date: 2026-04-14
Status: Drafted for review
Repo: `browser-cli`

## Summary

This spec defines a new three-skill system for browser-task delivery in the
`browser-cli` repository:

1. `browser-cli-delivery`
2. `browser-cli-explore`
3. `browser-cli-converge`

The new design replaces the idea of one large delivery skill with a layered
model:

- one user-facing orchestrator skill
- one exploration skill that captures durable feedback into `task.meta.json`
- one convergence skill that turns validated paths into `task.py`

The default completion state is a stable `task.py` plus `task.meta.json`.
`automation.toml` generation and `browser-cli automation publish` remain
optional, user-driven branches rather than mandatory output.

## Problem Statement

The current repository previously relied on a single delivery-oriented skill.

That skill points agents toward the right deliverables, but it still behaves
mostly like a linear checklist. It does not yet make the core feedback loop the
center of the workflow:

`explore -> try -> learn -> record reusable knowledge -> converge -> validate`

This gap matters because the current Browser CLI artifact model already expects
that reusable knowledge will survive beyond chat history:

- `task.py` holds executable logic
- `task.meta.json` holds structured environment assumptions, success-path
  knowledge, recovery hints, failures, and reusable site knowledge
- `automation.toml` wraps the task only when the user wants packaging or
  publication

Without a stronger skill contract:

- agents can jump from exploration straight to code
- durable lessons stay in chat instead of metadata
- `task.py` risks absorbing exploration-only trial logic
- `automation.toml` or publish can be attempted before the task is stable

## Repository Constraints

This design must align with the repository's current implementation, not an
imagined future API.

### Current Runtime And CLI Truths

- `src/browser_cli/task_runtime/flow.py` defines the high-level `Flow` surface
  for task execution
- `src/browser_cli/commands/task.py` defines the public task surfaces:
  `browser-cli task template`, `validate`, and `run`
- `src/browser_cli/commands/automation.py` defines the public automation
  surfaces including `publish`
- `tasks/_templates/task.meta.json` defines the full metadata structure the
  repository expects agents to work with
- `tasks/douyin_video_download/task.meta.json`,
  `tasks/interactive_reveal_capture/task.meta.json`, and
  `tasks/lazy_scroll_capture/task.meta.json` show the intended level of durable
  knowledge capture

### Important Observations

- `validate_task_metadata()` currently enforces required top-level sections and
  a valid `task` section, but not the full richness of the metadata template
- the skill should therefore treat the repository template and examples as the
  practical contract for good metadata, not only the minimum validator
- the skill must keep `task.py` as the only source of execution logic
- the skill must keep `automation.toml` and publish optional because the user
  may decline either one

## Goals

- Create a delivery workflow that is high-autonomy by default.
- Preserve `browser-cli` as the main browser execution backend.
- Make feedback capture into `task.meta.json` a first-class requirement.
- Keep `task.py` focused on validated execution paths only.
- Allow optional exploration and debugging work without weakening delivery
  discipline.
- Keep `automation.toml` generation and publish user-driven rather than
  mandatory.
- Make stage boundaries explicit so agents know when to explore, when to
  converge, and when to go back.

## Non-Goals

- This spec does not redesign the Browser CLI runtime itself.
- This spec does not add a public `browser-cli explore` command.
- This spec does not make publication mandatory for every task.
- This spec does not require every task to start from repository templates, as
  long as the final result matches the task contract.
- This spec does not turn `task.meta.json` into a transcript or raw log store.

## Options Considered

### 1. One larger replacement skill

Advantages:

- simple to discover
- fewer files

Disadvantages:

- mixes orchestration, exploration, and convergence rules together
- harder to maintain strict stage boundaries
- encourages large, vague instructions instead of explicit phase ownership

Rejected.

### 2. One delivery skill with optional embedded exploration guidance

Advantages:

- smaller surface area
- somewhat easier migration from the existing skill

Disadvantages:

- exploration remains secondary instead of first-class
- convergence rules are easier to bypass
- metadata feedback capture stays too weak

Rejected.

### 3. One orchestrator skill plus two focused child skills

Advantages:

- separates concerns cleanly
- matches the user's desired feedback loop
- lets the top-level skill manage stage transitions and rollback rules
- gives exploration and convergence each a clear artifact responsibility

Disadvantages:

- introduces more than one skill document
- requires cross-skill conventions

Chosen direction.

## Chosen Direction

The repository should add a three-layer skill system with short names:

1. `browser-cli-delivery`
2. `browser-cli-explore`
3. `browser-cli-converge`

### Role Split

- `browser-cli-delivery` is the user-facing orchestrator
- `browser-cli-explore` is responsible for real browser exploration and
  feedback capture into `task.meta.json`
- `browser-cli-converge` is responsible for implementing the validated path in
  `task.py`

`automation.toml` creation and `browser-cli automation publish` stay inside the
orchestrator as optional end-stage branches. They are not part of the default
definition of done.

## Skill Topology

### `browser-cli-delivery`

This is the only skill users should normally invoke directly for browser-task
delivery work.

Its responsibilities are:

- decide whether the task is ready for exploration
- decide when to invoke `browser-cli-explore`
- decide when exploration evidence is sufficient to invoke
  `browser-cli-converge`
- decide when validation failure should send the process back to exploration
- ask the user whether to generate `automation.toml`
- ask the user whether to publish

### `browser-cli-explore`

This skill owns:

- preflight context gathering relevant to the target site and environment
- choosing the exploration mode
- trying candidate browser paths with `browser-cli`
- capturing only durable findings
- updating `task.meta.json` with stable knowledge and reusable failure lessons

### `browser-cli-converge`

This skill owns:

- implementing the validated path in `task.py`
- keeping code aligned with metadata
- encoding waits, assertions, and artifacts explicitly
- validating the task with `browser-cli task validate`
- running `browser-cli task run` when the task needs runtime proof

## Artifact Responsibilities

The new skill system must preserve a strict artifact split.

### `task.py`

`task.py` is the single source of execution logic.

It should contain:

- the validated success path
- explicit waits and assertions
- helper functions needed for deterministic replay
- artifact writing logic that belongs to task execution

It should not contain:

- raw exploration branches
- speculative fallback paths that were never validated
- chat-derived guesses standing in for evidence

### `task.meta.json`

`task.meta.json` is the durable sidecar for reusable knowledge gathered during
exploration and refined during convergence.

The skill system should treat these sections as the core feedback sink:

- `environment`
- `success_path`
- `recovery_hints`
- `failures`
- `knowledge`

The metadata should capture:

- environment assumptions
- stable execution steps
- key semantic refs or anchor patterns
- known wait points
- alternate paths when validated
- reusable failure lessons
- site-specific behavior such as lazy load, pagination, anti-bot, or
  browser-state requirements

The metadata should not capture:

- raw logs
- unfiltered transcripts
- every exploratory dead end
- verbose artifact inventories with no future decision value

### `automation.toml`

`automation.toml` is optional.

It should be created only when the user wants packaging or publication.
It must not become a second implementation layer for browser logic.

## Default Done Criteria

The default done state for the new workflow is:

- a stable `task.py`
- a meaningful `task.meta.json`
- validation through `browser-cli task validate`
- runtime proof through `browser-cli task run` when needed by the task shape

The process may stop there.

Additional completion states are allowed only when the user asks for them:

- generation of `automation.toml`
- publication via `browser-cli automation publish`

## Stage Model

The orchestrator should manage a strict state machine rather than a loose
checklist.

### 1. Preflight

The orchestrator must verify:

- `browser-cli` is usable
- the Python environment that will run the task is understood
- browser/profile assumptions are known
- site constraints such as login, cookies, locale, or writable artifacts are
  known

If the live daemon and documented CLI appear out of sync, one
`browser-cli reload` is allowed before declaring a capability gap.

If critical prerequisites are missing, the process stops with a fix plan. It
does not enter exploration blindly.

### 2. Explore

The orchestrator invokes `browser-cli-explore` to determine the task mode and
test the smallest viable path.

Expected exploration modes include:

- ref-driven
- content-first
- lazy-scroll
- login-state-first
- browser-state or network-assisted

The exploration goal is not "browse around until success". It is to validate
which path is repeatable and what must be recorded for replay.

### 3. Feedback Capture

After each meaningful exploration round, durable findings should be distilled
into `task.meta.json`.

This is a rolling process, not a single final documentation step.

The rules are:

- validated success behavior belongs in `success_path`
- repeatable waits, alternate routes, and stale-ref handling belong in
  `recovery_hints`
- reusable failures belong in `failures`
- site behavior patterns belong in `knowledge`

### 4. Converge

The orchestrator invokes `browser-cli-converge` only when:

- the success path is sufficiently clear
- the key assertions are known
- the fragile points and recovery logic are understood well enough to encode

Convergence should turn evidence into deterministic task code.

### 5. Validate

Validation always starts with:

- `browser-cli task validate <task-dir>`

If the task depends on runtime behavior or real inputs, the process should also
use:

- `browser-cli task run <task-dir> ...`

When validation fails, the orchestrator must decide whether the failure is:

- an implementation bug inside the converged path
- or an evidence gap that requires returning to exploration

If the metadata or explored evidence is insufficient, the process must go back
to exploration instead of stacking guesses in code.

### 6. Optional Automation

Only after the default done state is reached should the orchestrator ask the
user whether to:

- generate `automation.toml`
- publish through `browser-cli automation publish`

Both remain optional.

## Skill Contracts

### Contract For `browser-cli-delivery`

Required behavior:

- act as the main user-facing skill
- target `task.py` plus `task.meta.json` as the default endpoint
- invoke `browser-cli-explore` and `browser-cli-converge` when appropriate
- manage rollback from validation back to exploration
- keep `automation.toml` and publish behind explicit user choice

Prohibited behavior:

- treating one successful exploration as sufficient without checking stability
- skipping metadata capture and writing only `task.py`
- publishing by default

### Contract For `browser-cli-explore`

Required behavior:

- use `browser-cli` as the primary browser execution path
- choose and validate the exploration mode
- gather only observations that change the next decision
- write durable learnings into `task.meta.json`
- stop once there is enough validated evidence to implement the task

Prohibited behavior:

- turning exploration code directly into the final `task.py`
- recording raw logs or chat transcripts in metadata
- promoting one-off page behavior into stable knowledge

### Contract For `browser-cli-converge`

Required behavior:

- keep `task.py` as the only execution-logic truth source
- route browser interactions through `browser_cli.task_runtime.Flow`
- align task code with `task.meta.json`
- use repository task commands for validation
- keep temporary exploration-only logic out of the final task

Prohibited behavior:

- bypassing the Browser CLI task runtime as the main path
- allowing metadata and code to describe different workflows
- encoding unsupported guesses as waits, selectors, or alternate flows

## Content Structure For The New Skill Files

Each new `SKILL.md` should use the same compact structure:

1. `Overview`
2. `When to Use`
3. `Hard Rules`
4. `Phase Order`
5. `Done Criteria`
6. `Common Mistakes`

The content should stay concrete and repository-aware rather than generic.

## Suggested File Layout

```text
skills/
  browser-cli-delivery/
    SKILL.md
  browser-cli-explore/
    SKILL.md
  browser-cli-converge/
    SKILL.md
```

Legacy single-skill guidance may be reused as source material, but it should
not remain the primary design shape if it prevents the new layered model.

## Migration Guidance

This design allows the old single-skill layout to be retired after references
have been updated.

A safe migration path is:

1. add the three new skills
2. port the reusable repository-specific guidance into the new skills
3. update references or documentation that point to the legacy layout
4. remove the legacy directory once the repository no longer depends on it

## Open Questions

These questions do not block the design, but they should be resolved during
implementation:

- whether `browser-cli-delivery` should reference the old skill during the
  transition period
- whether the new skills need shared reference files beyond their `SKILL.md`
- whether repository docs should point users at the new top-level skill once it
  exists

## Acceptance Criteria

The design is satisfied when:

- the repository contains the three new skills with clear role boundaries
- the top-level skill defaults to `task.py` plus `task.meta.json`
- the exploration skill explicitly treats `task.meta.json` as the durable
  feedback sink
- the convergence skill explicitly treats `task.py` as the only execution
  logic artifact
- optional automation generation and publish remain gated by explicit user
  choice
- the resulting guidance matches the current Browser CLI runtime and CLI
  surfaces
