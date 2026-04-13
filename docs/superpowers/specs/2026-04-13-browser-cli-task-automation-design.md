# Browser CLI Task And Automation Surface Design

Date: 2026-04-13
Status: Drafted for review
Repo: `/home/hongv/workspace/browser-cli`

## Summary

Browser CLI should stop using `workflow` as the primary user-facing concept for
task execution and publication.

The product should instead expose two distinct layers:

- `task`: local, editable source artifacts created and refined by an agent
- `automation`: published, versioned, service-managed snapshots derived from a
  task

The current `workflow` surface mixes those two layers. That is the main source
of confusion for `pip` users who do not live inside this repository and do not
want to think in terms of `workflow.toml` before they even have a runnable task.

This spec replaces the public `workflow` concept with a clearer model:

- `task.py` + `task.meta.json` are the source task contract
- `browser-cli task ...` is the local authoring and validation surface
- `browser-cli automation ...` is the published runtime and service surface
- publication creates a durable snapshot and does not keep pointing at the
  mutable source task directory

## Problem Statement

Today the public product shape is inconsistent:

- the exploration skill says successful work should converge to
  `task.py + task.meta.json`
- the public CLI exposes `workflow run` and `workflow validate` instead of a
  first-class `task` surface
- the repository documents `tasks/<name>/...` as a layout, but `pip` users are
  not given a canonical default task workspace
- the workflow service persists source file paths rather than treating a
  published definition as a durable snapshot

This creates several problems:

- users have to learn `workflow` before they can simply run a task
- `workflow` sounds like orchestration logic rather than a published automation
  object
- publication semantics are weak because service definitions can break when
  source paths move
- if `task init` is the only way to stay consistent, agent-generated tasks gain
  unnecessary friction

## Goals

- Make `pip` users the primary UX target.
- Give tasks a canonical filesystem contract outside the source repo.
- Make local execution and validation task-first.
- Make publication create a durable, versioned automation snapshot.
- Ensure published automations are the source of truth for service execution.
- Keep `task.py` execution routed through `browser_cli.task_runtime`.
- Remove the public `workflow` naming from the product surface.
- Make skill-driven task generation safe even without a CLI scaffolding command.

## Non-Goals

- No second browser runtime.
- No declarative replacement for `task.py`.
- No automatic two-way sync between source tasks and published automations.
- No requirement to keep `workflow` command compatibility.
- No need for `task init` in the first release of this redesign.

## Options Considered

### 1. Keep `workflow`, add a thin `task` alias

Advantages:

- smallest code movement
- easiest short-term migration

Disadvantages:

- keeps the existing concept overlap
- preserves the wrong first-run UX for `pip` users
- continues the ambiguity between source task and published object

Rejected.

### 2. Move everything under `task`

Advantages:

- very simple top-level CLI
- one obvious noun for users

Disadvantages:

- blurs the boundary between source artifacts and published runtime state
- makes scheduling, service status, import/export, and versioned publication
  look like source-task concerns

Rejected.

### 3. Split into `task` and `automation`

Advantages:

- matches the real lifecycle boundary
- gives `pip` users a clear local-first workflow
- lets publication mean a durable, versioned object
- gives the service layer a better product name than `workflow`

Disadvantages:

- requires public surface renaming
- requires migration of docs, guards, and service terminology

Chosen direction.

## Chosen Direction

Browser CLI should expose three durable concepts:

1. `task`
2. `automation`
3. `run`

The meaning of each concept is:

- `task`: source code and structured task metadata under local user control
- `automation`: a published, versioned snapshot with runtime config, schedule,
  outputs, service identity, and operational state
- `run`: a single execution of an automation version

The key rule is:

- source tasks are edited locally
- published automations are immutable snapshots for execution purposes
- changes to a task affect service behavior only after a new publish

## Public CLI Surface

### `task`

First-release public commands:

- `browser-cli task run <task-dir>`
- `browser-cli task validate <task-dir>`

`task init` is intentionally not required in the first release.

Agents may create task directories directly as long as they satisfy the task
contract. This removes an unnecessary scaffolding step from the main happy path.

`task run` should accept the same input override model already used by
`workflow run`:

- `--set KEY=VALUE`
- `--inputs-json JSON`

### `automation`

Public commands:

- `browser-cli automation publish <task-dir>`
- `browser-cli automation import <automation.toml>`
- `browser-cli automation export <automation-id> --output <path>`
- `browser-cli automation ui`
- `browser-cli automation status`
- `browser-cli automation stop`

`automation publish` is the only public bridge from source task to published
automation.

### Removed Public Surface

The following public commands should be removed rather than kept as compatible
aliases:

- `browser-cli workflow run`
- `browser-cli workflow validate`
- `browser-cli workflow import`
- `browser-cli workflow export`
- `browser-cli workflow ui`
- `browser-cli workflow service-status`
- `browser-cli workflow service-stop`

The public file name `workflow.toml` should also be replaced by
`automation.toml`.

## Filesystem Layout

### Source Tasks

Canonical default location for user-created tasks:

```text
~/.browser-cli/tasks/<task-id>/
  task.py
  task.meta.json
```

This location is the default contract for `pip` users. It does not prevent
future support for explicit alternative paths, but the product should document
this location as the primary workspace.

### Published Automations

Canonical default location for published automation snapshots:

```text
~/.browser-cli/automations/<automation-id>/
  versions/<version>/
    task.py
    task.meta.json
    automation.toml
    publish.json
  runs/<run-id>/
    result.json
    run.log
    ...
```

This structure separates:

- source authoring
- published definitions
- run artifacts

## Task Contract

Every valid task directory must contain:

- `task.py`
- `task.meta.json`

### `task.py`

`task.py` must satisfy the following contract:

- expose a callable entrypoint named `run`
- use the signature `run(flow, inputs)`
- return a machine-readable `dict`
- route browser actions through `browser_cli.task_runtime`
- not use direct Playwright or raw daemon handling as the primary execution path

### `task.meta.json`

`task.meta.json` must remain structured and must not become a transcript dump.

It must continue to capture reusable task knowledge such as:

- task identity and intent
- environment assumptions
- success path summary
- recovery hints
- durable failure learnings
- knowledge that helps future reruns or future publication

## Validation Model

`browser-cli task validate <task-dir>` must be a strong validation step.

It should validate:

- required files exist
- `task.meta.json` matches the schema
- `task.py` can be loaded
- the `run` entrypoint exists and is callable
- the entrypoint shape matches the task contract closely enough to reject common
  invalid agent output before runtime

The purpose is to catch task contract drift before publication or service use.

## Publication Model

`browser-cli automation publish <task-dir>` should:

1. validate the source task
2. resolve or create the stable automation id for that task lineage
3. compute the next version number
4. materialize a new snapshot under the automation versions directory
5. generate `automation.toml`
6. write publication metadata to `publish.json`
7. import the snapshot into the automation service automatically

Default behavior is intentionally opinionated:

- publish creates a new version
- publish imports it into the service
- publish does not keep the service pointed at the mutable source task path

## Automation Identity And Versioning

Each automation has:

- one stable `automation_id`
- many published versions

Each publish increments the version while preserving the stable id.

This allows:

- stable UI identity
- stable scheduling and history grouping
- explicit traceability from runs to the exact published definition used

Every run record must retain:

- `automation_id`
- `automation_version`
- snapshot path

## Automation Source Of Truth

Once publication succeeds, the automation snapshot becomes the source of truth
for execution.

The source task remains editable, but it is only the source for a future publish.

There is no implicit sync in either direction:

- editing the source task does not mutate the published automation
- editing automation configuration in the UI does not rewrite the source task

This keeps publication semantics honest and prevents hidden drift.

## Runtime Boundary

The redesign must preserve the existing runtime principle:

- Browser CLI daemon and `browser_cli.task_runtime` remain the execution
  substrate for both local task runs and published automation runs

This means:

- `task run` executes the source `task.py` through `Flow`
- automation service executes the published snapshot `task.py` through the same
  `Flow` abstraction
- the service does not introduce a second browser execution stack

## Skill And Documentation Changes

Because first release does not require `task init`, consistency must come from
task contract documentation, validation, and skill behavior.

The `browser-cli-explore-delivery` skill should be upgraded to a stronger task
generation contract.

It should include:

- a canonical `task.py` template
- a canonical `task.meta.json` template
- explicit must / must-not rules
- clear separation between task concerns and automation concerns
- an instruction that successful task generation must end with
  `browser-cli task validate <task-dir>` rather than relying on publication to
  discover malformed files

Human-facing docs should be updated to explain:

- the default task workspace under `~/.browser-cli/tasks`
- the difference between source tasks and published automations
- the difference between a published automation and a run

## Service Boundary

The current workflow service should be renamed conceptually and publicly to an
automation service.

Its responsibilities remain legitimate, but they belong to `automation`, not
to `task`:

- persist published definitions
- own enable / disable state
- own schedule configuration
- own output configuration
- own import / export
- own UI and service status
- own run history

These concerns should not move into the task layer.

## Migration

This redesign intentionally chooses clarity over command compatibility.

Recommended migration approach:

1. remove public `workflow` CLI registration
2. introduce `task` and `automation` CLI groups
3. rename workflow manifest handling to automation manifest handling
4. rename workflow service messaging and docs to automation service
5. update README, AGENTS guidance, examples, guards, and tests together

The existing internal code can be reused where appropriate, but the public
surface should not preserve the old naming simply to avoid change.

## Error Handling

Errors should clearly identify the active object type.

Recommended error categories:

- task validation errors
- task runtime errors
- automation publication errors
- automation service errors
- automation run errors

Messages should explicitly say `task` or `automation` rather than using generic
or legacy `workflow` wording.

## Testing

At minimum, implementation should cover:

- `task run` with `task-dir` input
- `task validate` schema and entrypoint validation
- direct agent-created task directories under `~/.browser-cli/tasks`
- `automation publish` snapshot creation
- automatic import on publish
- stable automation id plus incrementing versions
- service execution from snapshot paths rather than source task paths
- `automation import` / `automation export` round trips
- CLI help text and parser shape after `workflow` removal
- doc and guard updates that reflect the renamed public model

## Decision Summary

The product should move from:

- source task artifacts hidden behind a `workflow` execution surface

to:

- `task` as the local authoring surface
- `automation` as the published and operated surface
- snapshot-based publication with stable automation identity and explicit
  versioning

This better matches the actual lifecycle of Browser CLI automation, gives `pip`
users a cleaner entry point, and removes a public noun that currently describes
the wrong thing.
