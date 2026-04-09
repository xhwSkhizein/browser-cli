# Browser CLI Explore, Task, and Workflow Design

Date: 2026-04-09
Status: Drafted for review
Repo: `/Users/hongv/workspace/m-projects/browser-cli`

## Summary

This phase defines everything that comes **after** Browser CLI primitives and
semantic refs, but **before** a user-facing workflow product is implemented.

The key correction is:

- `explore` is **not** a `browser-cli` subcommand
- `browser-cli` remains the stable browser execution substrate
- `explore` is an agent activity that accepts a goal, uses Browser CLI to try
  and verify actions, and converges on a deterministic execution path
- the output of exploration is a replayable task artifact
- a `workflow` is a published wrapper around a task, not a second copy of task
  logic

The concrete artifact model is:

- `task.py`
- `task.meta.json`
- later, `workflow.toml`

## Dependency Order

The intended dependency order is now:

1. `v1`: one-shot read
2. `v2`: daemon-backed browser actions
3. `v3a`: semantic ref resolution
4. `v3b`: exploration artifact model
5. `v4`: published workflow wrapper and runner

This spec covers `v3b` and the shape of `v4`, but does not authorize
implementation of the workflow runner before `v3a` is complete.

## Problem Statement

After `v2`, Browser CLI has enough primitive browser actions to solve real web
automation tasks, but it still lacks a durable way to convert an agent's trial
and error process into a reusable asset.

Without a formal artifact model:

- exploration remains trapped in chat history
- the same site knowledge must be rediscovered repeatedly
- failures and recovery lessons are not reusable
- replay depends on ad hoc agent reasoning instead of a stable executable task
- workflow delivery risks becoming a second implementation layer that drifts
  from the original task logic

The system needs a path from:

`goal -> agent exploration -> deterministic task artifact -> published workflow`

without duplicating business logic across those stages.

## Goals

- Treat exploration as an agent process, not as a Browser CLI subcommand.
- Produce a replayable task artifact from successful exploration.
- Allow the task artifact to remain human-readable and easy for agents to edit.
- Preserve Browser CLI as the single browser execution substrate.
- Keep the task artifact expressive enough for retries, branching, loops, and
  local helper logic.
- Separate deterministic execution logic from exploration history and task
  knowledge.
- Make workflow publication a thin packaging layer over a task.
- Support future scheduling, outputs, notifications, and post-run hooks through
  workflow config, not by rewriting the task.

## Non-Goals

- No `browser-cli explore ...` public command in this phase.
- No attempt to encode all task logic in TOML or another declarative DSL.
- No requirement that agents manually preserve raw exploration transcripts.
- No second browser runtime that bypasses Browser CLI daemon actions.
- No direct Playwright usage inside task artifacts as the primary path.
- No marketplace, registry, or distribution system in this spec.

## Options Considered

### 1. Declarative workflow first

Advantages:

- highly structured
- easier to validate mechanically

Disadvantages:

- poor fit for complex web tasks
- forces an early DSL before enough execution knowledge exists
- makes exploration-to-artifact conversion unnatural

Rejected.

### 2. Free Python task only

Advantages:

- natural for agents and developers
- expressive enough for real-world control flow

Disadvantages:

- no clear place for durable task knowledge, failure learnings, or publication
  metadata
- workflow publication would likely re-implement configuration in code

Rejected as incomplete.

### 3. Free Python task plus structured metadata plus workflow wrapper

Advantages:

- keeps task execution flexible
- keeps knowledge and failure learnings structured
- gives workflow publication a stable contract
- avoids a declarative DSL bottleneck

Disadvantages:

- introduces multiple files per task
- requires explicit conventions for what lives where

Chosen direction.

## Chosen Direction

The system should use a three-layer artifact model:

1. `task.py`
2. `task.meta.json`
3. `workflow.toml` for publication

The roles are:

- `task.py` is the executable, replayable implementation
- `task.meta.json` is the structured exploration and task-knowledge sidecar
- `workflow.toml` is the published runtime wrapper for user-facing delivery

The task remains the single source of execution logic. A workflow packages a
task for delivery and operation; it does not replace the task's implementation.

## Product Shape

### Explore

Explore is an agent behavior:

- input: a user goal or task
- tools: Browser CLI actions and future task runtime helpers
- process: iterative trial, observation, validation, and convergence
- output: a deterministic task artifact

Explore is not part of the Browser CLI end-user command tree.

### Task

A task is the technical artifact produced by successful exploration.

It should be replayable, editable, inspectable, and testable.

### Workflow

A workflow is the published, user-facing packaging of a task.

It answers questions such as:

- when should this run?
- what inputs should be provided?
- where should outputs go?
- what hooks should run before or after execution?
- what operational metadata should a user see?

It does **not** answer browser interaction questions already solved in the task.

## Artifact Layout

Recommended layout:

```text
tasks/
  xiaohongshu_author_stats/
    task.py
    task.meta.json
    workflow.toml
    artifacts/
```

Alternative layouts may be used later, but the logical grouping must remain:

- one task directory
- one executable task file
- one structured metadata file
- optional one workflow wrapper file

## `task.py`

### Role

`task.py` is the replayable implementation of the discovered execution path.

It is intentionally allowed to be free Python because:

- agents reason well in Python
- loops, retries, branching, and helper functions are often needed
- forcing a DSL too early would reduce productivity and increase friction

### Constraint Model

`task.py` is free Python in syntax, but browser operations must enter through a
thin Browser CLI runtime SDK.

This means:

- free control flow is allowed
- direct Playwright usage is not the primary supported path
- direct daemon protocol calls are not the primary supported path
- shelling out to `browser-cli` directly should be unnecessary once the runtime
  SDK exists

### Runtime Shape

The runtime should be thin and explicit, for example:

- `browser_cli.task_runtime.client`
- `browser_cli.task_runtime.flow`
- `browser_cli.task_runtime.models`

Representative usage:

```python
from browser_cli.task_runtime.flow import Flow


def run(flow: Flow, inputs: dict) -> dict:
    flow.open(inputs["url"])
    flow.snapshot()
    flow.click("@8d4b03a9")
    flow.wait_text("Revealed", timeout=5)
    return {"html": flow.html()}
```

### Parameter Model

Tasks should use a mixed parameter model:

- default values may be embedded for convenience
- external input overrides must be supported structurally

This keeps ad hoc replay easy while still allowing publication as a reusable
workflow.

### Allowed Complexity

The task should support:

- helper functions
- retries
- bounded loops
- conditional branches
- assertions and verification
- local normalization of task outputs

The task should avoid:

- unbounded hidden browser state
- direct dependence on chat history
- duplicated workflow packaging logic

## `task.meta.json`

### Role

`task.meta.json` is the structured sidecar for both:

- execution assistance
- long-lived task knowledge and exploration learnings

It exists so that `task.py` can stay focused on the success path and runtime
logic, while the metadata file carries the durable context that future agents
and workflow tooling need.

### Design Principle

The file should not be a raw transcript or step-by-step debug log.

It should contain distilled, reusable information with high value density.

### Top-Level Sections

Recommended top-level structure:

- `task`
- `environment`
- `success_path`
- `recovery_hints`
- `failures`
- `knowledge`

### `task`

Purpose:

- identify the task
- describe the goal
- define inputs and expected outputs

Suggested fields:

- `id`
- `name`
- `goal`
- `inputs`
- `expected_outputs`

### `environment`

Purpose:

- capture assumptions required for correct execution

Suggested fields:

- `site`
- `entry_url`
- `requires_login`
- `agent_scope`
- `profile_expectation`
- `browser_assumptions`

### `success_path`

Purpose:

- summarize the validated path that the task implements

Suggested fields:

- `steps`
- `key_refs`
- `key_assertions`
- `artifacts`

This section is especially important for future agents that need to understand
the task quickly without re-reading code line-by-line.

### `recovery_hints`

Purpose:

- help future agents repair or resume a task without rediscovering everything

Suggested fields:

- `retryable_steps`
- `alternate_paths`
- `stale_ref_strategy`
- `known_wait_points`
- `anti_bot_recovery`

### `failures`

Purpose:

- preserve only failures with future diagnostic value

Suggested fields:

- `attempt`
- `step`
- `reason`
- `signal`
- `resolution`

The rule is simple:

- keep failures that teach something reusable
- discard transient noise and raw trace spam

### `knowledge`

Purpose:

- preserve durable site or task knowledge useful across multiple tasks

Suggested fields:

- `stable_selectors_or_roles`
- `semantic_ref_notes`
- `pagination_pattern`
- `lazy_load_pattern`
- `anti_bot_notes`
- `output_interpretation_notes`

### Why the Sidecar Exists

`task.meta.json` enables future systems to:

- support lower-token execution and maintenance
- let new agents continue work without re-exploring from scratch
- upgrade a task into a workflow without scraping comments from Python code
- build future task registries or recommendation systems from structured data

## `workflow.toml`

### Role

`workflow.toml` is the published wrapper around a task.

It must not duplicate browser action logic from `task.py`.

Its responsibilities are operational and user-facing:

- scheduling
- input defaults and overrides
- output destinations
- runtime policies
- notifications and hooks
- workflow identity and description

### Why TOML

TOML is the chosen format because:

- it is config-shaped rather than code-shaped
- it is more disciplined than YAML for this use case
- it keeps workflow packaging distinct from task implementation

### Recommended Sections

- `[workflow]`
- `[task]`
- `[inputs]`
- `[schedule]`
- `[outputs]`
- `[hooks]`
- `[runtime]`

### Suggested Fields

`[workflow]`

- `id`
- `name`
- `description`
- `version`

`[task]`

- `path`
- `meta_path`
- `entrypoint`

`[inputs]`

- default values
- environment overrides
- required/optional notes

`[schedule]`

- disabled/manual
- cron-like schedule or other future scheduling representation
- timezone

`[outputs]`

- stdout capture mode
- artifact directory
- webhook or callback targets
- user-facing delivery target

`[hooks]`

- `before_run`
- `after_success`
- `after_failure`

`[runtime]`

- retry policy
- timeout policy
- max concurrent runs
- logging level

## Relationship Between Task and Workflow

The relationship is intentionally one-way:

- a task can exist without a workflow
- a workflow depends on a task
- a workflow should not fork and re-implement task logic

In other words:

- `task.py` solves the task
- `workflow.toml` publishes the task

This keeps the system from drifting into dual maintenance.

## Execution Model

### Task Execution

Task execution should eventually look like:

1. load task
2. load inputs
3. initialize runtime flow/client
4. run task logic
5. produce structured outputs
6. write artifacts

### Workflow Execution

Workflow execution should eventually look like:

1. load `workflow.toml`
2. resolve task path and metadata
3. merge workflow inputs with runtime inputs
4. execute `task.py`
5. route outputs
6. run success or failure hooks

The workflow layer should not inspect browser details unless needed for
reporting.

## Failure Handling

### Task-Level Failure

The task runtime should expose structured errors for:

- browser action failures
- stale or ambiguous refs
- assertion failures
- timeout failures
- anti-bot or auth failures

`task.py` may choose to catch and handle some of these in Python, but the
underlying runtime should preserve typed information.

### Metadata-Level Failure Knowledge

When a task fails in a reusable way, `task.meta.json` should be updated with the
distilled lesson, not with the full stack trace.

### Workflow-Level Failure

Workflow-level configuration should decide:

- retry or not
- notify or not
- where to record failure artifacts
- which hook to trigger

## Explore-to-Task Convergence Rules

An agent should be considered finished exploring only when:

- it can replay the path without relying on chat memory
- the resulting `task.py` is deterministic enough to re-run
- key waits and assertions are explicit
- the sidecar captures any non-obvious recovery knowledge

The intended convergence model is:

1. explore freely
2. narrow to one validated path
3. encode that path in `task.py`
4. distill reusable knowledge into `task.meta.json`
5. optionally publish the task as a workflow

## Testing Strategy

### 1. Task Runtime Tests

- thin SDK request routing
- typed return values
- error mapping from Browser CLI JSON responses

### 2. Task Artifact Tests

- replay of sample `task.py` fixtures
- input override behavior
- artifact writing behavior
- deterministic assertions

### 3. Metadata Tests

- schema validation for `task.meta.json`
- required field checks
- failure entry normalization

### 4. Workflow Wrapper Tests

- TOML parsing
- task path resolution
- input merge behavior
- output routing and hook invocation

### 5. Integration Tests

- end-to-end run from workflow wrapper into task runtime into Browser CLI daemon
- success and failure paths using local fixture pages

## Migration and Rollout

Recommended rollout sequence:

1. finish `v3a` semantic ref resolution
2. build the thin Python task runtime
3. define a canonical `task.py` entrypoint convention
4. define `task.meta.json` schema and validation
5. add one or two reference tasks from local fixture scenarios
6. define `workflow.toml`
7. build a workflow runner that executes tasks without duplicating task logic

## Acceptance Criteria

This design is successfully implemented only when:

- exploration can converge into a reusable `task.py`
- `task.py` uses a thin Browser CLI runtime instead of direct Playwright as the
  primary path
- `task.meta.json` captures reusable execution and learning context
- `workflow.toml` packages task execution without re-implementing task logic
- a task can be replayed independently of the original conversation
- a workflow can run the same task with different inputs and operational
  configuration
