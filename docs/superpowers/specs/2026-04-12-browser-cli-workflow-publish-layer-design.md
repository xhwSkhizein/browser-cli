# Browser CLI Workflow Publish Layer Design

Date: 2026-04-12
Status: Drafted for review
Repo: `/Users/hongv/workspace/m-projects/browser-cli`

## Summary

Browser CLI's current `workflow` surface is a thin manifest loader and one-shot
runner around `task.py`. That is useful for local packaging, but it is not yet
the product layer needed for repeatable user delivery.

The next phase should define Workflow Publish Layer as a persistent local
service that:

- stores published workflow definitions
- schedules and repeatedly executes stable `task.py` artifacts
- exposes a local Web UI as the primary management surface
- keeps execution routed through existing `task.py + task runtime + browser daemon`
- treats `workflow.toml` as a publish/import/export format rather than the live
  runtime database

The key architectural rule remains unchanged:

- `task.py` is the only source of task execution logic
- workflow is the operational packaging, scheduling, and delivery layer
- browser daemon remains the browser execution substrate

## Problem Statement

The current repository can already produce stable task artifacts:

- `task.py`
- `task.meta.json`
- optionally `workflow.toml`

But the current workflow layer is still missing the product capabilities implied
by "publish":

- no persistent workflow registry
- no background scheduler
- no run queue or history
- no durable workflow enable/disable state
- no local management UI
- no separation between workflow runtime state and static manifest files

As a result, `workflow` is still closer to "run this wrapper now" than "publish
this task as a durable recurring automation."

## Goals

- Publish stable `task.py` artifacts into a persistent local workflow service.
- Support repeated execution through manual, interval, daily, and weekly
  schedules.
- Provide a local Web UI as the primary control plane.
- Allow users to configure:
  - task parameter overrides
  - schedule and repetition frequency
  - output locations
  - runtime policies such as timeout and retry count
- Preserve `task.py` as the only execution logic surface.
- Preserve the existing browser daemon as the browser execution backend.
- Keep workflow state durable across service restarts.
- Provide run history, failure visibility, and retry support.
- Keep CLI involvement minimal and focused on diagnostics or service recovery.

## Non-Goals

- No second browser runtime that bypasses the existing daemon.
- No workflow DSL that re-expresses browser actions from `task.py`.
- No remote multi-user workflow server in this phase.
- No complex cron DSL in the first version.
- No schema-driven parameter form generation in the first version.
- No artifact browser or general file manager in the Web UI.
- No marketplace or workflow registry beyond the local machine.

## Options Considered

### 1. Extend the existing browser daemon into a single all-in-one service

Advantages:

- simplest deployment story
- one process to supervise

Disadvantages:

- mixes browser lifecycle with workflow persistence and scheduling
- makes browser failures more likely to disrupt workflow state management
- breaks the current package responsibility split

Rejected.

### 2. Add a separate workflow service that calls into the existing browser daemon

Advantages:

- preserves the current daemon boundary
- gives workflow scheduling and persistence their own lifecycle
- keeps execution routed through existing Browser CLI contracts

Disadvantages:

- introduces service-to-service coordination
- requires explicit health and status reporting for two backends

Chosen internal architecture.

### 3. Expose one user-facing service while internally splitting process roles

Advantages:

- keeps user mental model simple
- allows internal separation without exposing backend complexity

Disadvantages:

- still requires the same internal complexity as option 2
- adds supervisor and unified status reporting work

Chosen user-facing product shape.

## Chosen Direction

Workflow Publish Layer should be a local persistent service that manages
published task definitions and their repeated execution.

To the user, this should feel like one Browser CLI background service. Internally,
it may use more than one process:

- browser daemon for browser state and actions
- workflow service for scheduling, persistence, queueing, and Web UI/API

Execution remains one-way:

`published workflow -> scheduler/trigger -> task runtime -> browser daemon`

This preserves the approved repository contract:

- workflow packages tasks
- workflow does not re-implement tasks
- browser internals stay out of workflow definitions

## Service Boundaries

### Browser Daemon

The existing browser daemon continues to own:

- browser startup and shutdown
- tabs and `X_AGENT_ID` behavior
- driver selection and rebinding
- semantic ref capture and action execution
- runtime lifecycle diagnostics

It does not own:

- workflow definitions
- workflow scheduling
- workflow run history
- Web UI state

### Workflow Service

The new workflow service owns:

- persistent workflow definition storage
- workflow enable/disable state
- next-run calculation
- run queue and executor
- run history and event logs
- local Web UI and local API
- import/export of published workflow definitions

It does not directly perform browser actions. It delegates execution to
`task.py` through the task runtime.

### Task Runtime Bridge

Workflow execution must continue to call:

- `task.py`
- `browser_cli.task_runtime`
- existing daemon-backed Browser CLI action contracts

This keeps `task.py` as the only execution logic surface and avoids a second
automation engine.

## Persistence Model

Workflow runtime state should no longer live in manifest files.

### Runtime Source Of Truth

Use SQLite under `BROWSER_CLI_HOME`, for example:

- `~/.browser-cli/workflows.db`

The database stores:

- published workflow definitions
- schedule configuration
- task input overrides
- enable/disable state
- last run and next run state
- run history and status
- pointers to logs and artifacts

### Artifact And Log Storage

Use the filesystem for large outputs, for example:

- `~/.browser-cli/workflows/<workflow-id>/runs/<run-id>/`

This directory stores:

- task result JSON
- stdout and stderr logs
- task-produced artifacts
- failure debug attachments when available

### `workflow.toml` Role

`workflow.toml` should be retained, but its role changes.

It is no longer the live runtime source of truth.

It becomes:

- a publish artifact checked into a repo
- an import/export format for workflow definitions
- a reviewable and portable contract for task packaging

The separation is:

- `task.py`: execution logic source of truth
- SQLite: runtime and scheduling source of truth
- `workflow.toml`: portable publish definition

This preserves portability without forcing files to act as a database.

## Data Model

The first version should define at least these persistent entities.

### `workflows`

Fields:

- `id`
- `name`
- `task_path`
- `task_meta_path`
- `entrypoint`
- `enabled`
- `definition_status`
- `schedule_kind`
- `schedule_payload_json`
- `timezone`
- `output_dir`
- `result_json_path`
- `input_overrides_json`
- `retry_attempts`
- `retry_backoff_seconds`
- `timeout_seconds`
- `created_at`
- `updated_at`
- `last_run_at`
- `next_run_at`

`definition_status` should at minimum support:

- `valid`
- `invalid`

`invalid` means the workflow exists as a published record, but it currently
cannot run because its task path, metadata, or schedule definition fails
validation.

### `workflow_runs`

Fields:

- `run_id`
- `workflow_id`
- `trigger_type`
- `status`
- `started_at`
- `finished_at`
- `error_code`
- `error_message`
- `result_json_path`
- `artifacts_dir`
- `log_path`

`trigger_type` should at minimum support:

- `manual`
- `scheduled`
- `retry`

`status` should at minimum support:

- `queued`
- `running`
- `success`
- `failed`
- `cancelled`

### `workflow_run_events`

This table stores structured progress events for UI timelines and debugging.

Representative events include:

- queued
- executor claimed
- browser daemon ready
- task started
- task finished
- task failed
- retry scheduled

The first version does not need highly granular workflow lifecycle states if
these event records are available.

## Scheduling Model

The first version should deliberately limit schedule complexity.

Supported schedule modes:

- `manual`
- `interval`
- `daily`
- `weekly`

Examples:

- every 15 minutes
- every 1 hour
- every day at 09:00
- every Monday at 09:00

This is intentionally narrower than a full cron language because the product
goal is reliable recurring execution, not schedule-language breadth.

### Queueing And Execution

Recommended flow:

1. workflow service loads enabled workflows on startup
2. scheduler calculates due runs
3. due runs are persisted as `queued`
4. executor claims queued runs
5. executor invokes task runtime against the published task
6. task runtime calls the browser daemon as needed
7. run result, logs, artifacts, and next-run state are persisted

Persisting runs before execution is important. It prevents a run from existing
only in memory and gives the UI durable visibility even if the service exits
mid-run.

### Concurrency Policy

The first version should optimize for stability:

- same workflow default `max_concurrent_runs = 1`
- if the previous run is still active, the next scheduled run should either be
  skipped with an event or queued without running concurrently
- global execution may start conservative and mostly serial

This keeps runtime interactions predictable while Browser CLI is still maturing
around long-lived daemon use.

### Retry Policy

The first version should support a simple retry model:

- `retry_attempts`
- `retry_backoff_seconds`

Do not add complex retry trees, infinite retries, or per-error retry routing in
this phase.

## Web UI

The local Web UI is the primary user control plane.

The first version should provide four core screens.

### 1. Workflow List

Display:

- workflow name
- enabled/disabled status
- schedule summary
- last run result
- next run time
- `Run now` action

### 2. Workflow Detail And Edit

Allow editing:

- workflow identity
- task path, metadata path, entrypoint
- parameter overrides in a simple text or JSON/TOML editing area
- schedule mode and schedule settings
- output location
- timeout and retry configuration
- enable/disable state

Also show a recent run summary on the same page.

The first version does not need automatic task-schema form generation.

### 3. Run History

For each workflow, show:

- started and finished timestamps
- trigger source
- success or failure
- error summary
- log view action
- retry action

### 4. Run Detail

Show:

- current or final status
- event timeline
- stdout and stderr or structured logs
- result JSON path
- artifacts directory
- failure reason

## Local API

The Web UI should call a workflow-service-local API rather than the browser
daemon directly.

Recommended endpoints:

- `GET /api/workflows`
- `POST /api/workflows`
- `GET /api/workflows/{id}`
- `PUT /api/workflows/{id}`
- `POST /api/workflows/{id}/enable`
- `POST /api/workflows/{id}/disable`
- `POST /api/workflows/{id}/run`
- `GET /api/workflows/{id}/runs`
- `GET /api/runs/{run_id}`
- `POST /api/runs/{run_id}/retry`
- `GET /api/service/status`

The API is local-only in this phase and should default to loopback binding.

## CLI Role

The CLI should remain available, but only for diagnostics and service control.

Representative CLI responsibilities:

- service status
- workflow service health
- browser daemon health
- reload or reset operations
- import/export or validation helpers when needed

The CLI should not be the primary workflow management surface in this phase.

## Failure Model

Errors should remain attributable to the correct layer.

### Definition Errors

Examples:

- missing `task.py`
- invalid `task.meta.json`
- invalid schedule payload

These should block save/publish or mark the workflow as `invalid`.

### Scheduling Errors

Examples:

- next-run calculation failure
- corrupted workflow definition state

These belong to workflow service internals and should not be reinterpreted as
browser failures.

### Execution Errors

Examples:

- task entrypoint exceptions
- task timeout
- browser action failure
- stale or ambiguous semantic refs

These belong to an individual run and should be visible in run history.

### Browser Substrate Errors

Examples:

- browser daemon unavailable
- driver unavailable
- profile conflict

These should be recorded as run failures, while preserving the existing browser
daemon error semantics rather than inventing a second browser error model.

## Repository Impact

This phase should add or expand package areas such as:

```text
src/browser_cli/
  workflow/
    models.py
    loader.py
    runner.py
    service/
    scheduler/
    persistence/
    api/
    web/
tests/
  unit/
  integration/
docs/
  superpowers/specs/
```

The exact module split may differ, but the package boundaries should preserve:

- browser daemon for browser behavior
- workflow service for workflow lifecycle
- task runtime for task execution bridging

## Acceptance Criteria

- At least two real tasks can be published into the workflow service.
- At least one published workflow can run repeatedly on a non-manual schedule.
- The Web UI can:
  - create or import a workflow
  - edit task parameters
  - edit schedule configuration
  - enable or disable a workflow
  - run a workflow immediately
  - view run history
  - inspect a failed run
  - retry a failed run
- Workflow definitions persist across workflow-service restarts.
- Runtime execution still flows through `task.py + browser_cli.task_runtime +
  browser daemon`.
- Browser daemon outages become explicit run failures with durable diagnostics.
- `workflow.toml` remains usable as an import/export contract, but not as the
  runtime source of truth.
- CLI diagnostics can show enough information to distinguish browser-daemon
  health from workflow-service health.

## Testing Requirements

The implementation should cover at least:

- workflow definition persistence and reload
- schedule next-run calculation
- queueing and executor claiming
- manual run triggering
- retry flow
- run history state transitions
- browser daemon unavailable failure capture
- local API CRUD behavior
- local API run and retry behavior
- one or more integration tests proving scheduled execution drives the existing
  task runtime path

## Open Implementation Notes

This design intentionally leaves several implementation choices open for the
next planning step:

- whether the workflow service and browser daemon are launched under one
  supervisor command or separately
- which local Web stack is the lightest acceptable fit for the repository
- whether import/export is implemented as CLI commands, UI actions, or both

Those are implementation-planning concerns rather than design blockers. The
architectural decisions in this document are the durable constraints:

- Web UI is the primary management surface
- runtime state is persistent and service-owned
- `workflow.toml` is a publish artifact, not the runtime database
- `task.py` remains the sole execution logic surface
