# Browser CLI Workflow Publish Layer Implementation Plan

Date: 2026-04-12
Status: Ready for implementation
Related spec:

- `/Users/hongv/workspace/m-projects/browser-cli/docs/superpowers/specs/2026-04-12-browser-cli-workflow-publish-layer-design.md`

## Planning Note

The expected `writing-plans` skill was not available in the current
environment. This document is the direct planning fallback and serves the same
purpose: an implementation-ready sequence for the Workflow Publish Layer.

## Objective

Build Workflow Publish Layer as a persistent local Browser CLI service that:

- publishes stable `task.py` artifacts as durable workflow definitions
- stores workflow runtime state in a local persistence layer
- schedules and repeatedly executes tasks
- exposes a local Web UI as the primary control plane
- preserves `task.py + browser_cli.task_runtime + browser daemon` as the only
  execution path
- keeps `workflow.toml` as an import/export and review artifact rather than the
  runtime database

## Out Of Scope

The following are excluded from this implementation plan:

- a second browser runtime or direct Playwright execution path for workflows
- remote multi-user workflow hosting
- a full cron parser or advanced schedule DSL
- schema-generated task parameter forms
- an artifact file explorer in the Web UI
- a marketplace or workflow registry
- replacing the current browser daemon with the workflow service

## Delivery Strategy

Build this work in seven milestones:

1. workflow-service foundation and runtime paths
2. persistence model and schedule computation
3. run queue and task execution bridge
4. local API and service lifecycle
5. Web UI management surface
6. import/export, CLI diagnostics, and examples
7. hardening, docs sync, and end-to-end verification

The order matters:

- persistence and schedule state must exist before the Web UI can become the
  source of truth
- the execution bridge must land before scheduling is allowed to trigger real
  runs
- diagnostics and docs must reflect the new split between browser daemon and
  workflow service before the feature is considered complete

## Design Constraints To Preserve

Implementation must preserve these approved rules:

- `task.py` remains the sole execution logic surface.
- `workflow.toml` remains packaging, not duplicated task logic.
- browser daemon remains responsible for browser lifecycle and page actions.
- workflow service owns workflow definitions, scheduling, history, and UI state.
- runtime execution continues through `browser_cli.task_runtime`.
- persistent runtime state belongs to the service, not manifest files.
- CLI is secondary in this phase and should focus on diagnostics and service
  recovery.

## Target Repository Shape

Expected package expansion:

```text
src/browser_cli/
  commands/
  daemon/
  task_runtime/
  workflow/
    api/
    persistence/
    scheduler/
    service/
    web/
tests/
  unit/
  integration/
docs/
  superpowers/specs/
  superpowers/plans/
  examples/
tasks/
```

The exact module names may shift slightly, but the ownership split should stay:

- `browser_cli.daemon`: browser runtime
- `browser_cli.workflow.service`: workflow runtime
- `browser_cli.workflow.persistence`: local DB and filesystem state
- `browser_cli.workflow.scheduler`: next-run calculation and queueing
- `browser_cli.workflow.api`: local HTTP endpoints
- `browser_cli.workflow.web`: static UI assets or templates

## Milestone 1: Workflow-Service Foundation And Runtime Paths

### Deliverables

- workflow-service package skeleton
- local runtime path model for workflow DB, logs, and artifacts
- workflow-service process entrypoint
- service health model independent of browser daemon health

### Tasks

1. Expand `browser_cli.constants` or a workflow-local equivalent to define
   durable workflow-service paths under `BROWSER_CLI_HOME`.
   Minimum paths:
   - workflow DB path
   - workflow run-artifacts root
   - workflow service log path
   - workflow service run-info or socket metadata

2. Create workflow-service package skeleton under `src/browser_cli/workflow/`.
   Expected areas:
   - `service/`
   - `persistence/`
   - `scheduler/`
   - `api/`
   - `web/`

3. Add a workflow-service bootstrap entrypoint that can be started, stopped, and
   health-checked without pulling browser state into the same process by
   default.

4. Define service status models that distinguish:
   - workflow service health
   - browser daemon reachability
   - scheduler health
   - queue depth

5. Add unit tests for workflow-service path resolution under custom
   `BROWSER_CLI_HOME`.

### Acceptance Criteria

- Workflow-service paths are centralized rather than hard-coded.
- Workflow service can start without owning a browser session.
- Service status can report workflow-runtime health independently of browser
  health.

## Milestone 2: Persistence Model And Schedule Computation

### Deliverables

- SQLite-backed workflow definition store
- SQLite-backed run-history store
- schedule model restricted to manual, interval, daily, and weekly
- next-run calculation helpers
- invalid-definition detection

### Tasks

1. Implement the first database schema using stdlib `sqlite3`.
   Minimum tables:
   - `workflows`
   - `workflow_runs`
   - `workflow_run_events`

2. Define repository-layer models for persisted workflow definitions and run
   records.

3. Implement create, update, load, list, enable, and disable operations for
   workflows.

4. Implement validation for persisted workflow definitions.
   Minimum checks:
   - task path exists
   - task metadata path exists
   - task metadata validates
   - entrypoint is non-empty
   - schedule payload matches the chosen schedule mode

5. Define the supported schedule payloads.
   Recommended minimum:
   - `manual`
   - `interval`: minutes or seconds-based repeat interval
   - `daily`: local time of day
   - `weekly`: weekday plus local time of day

6. Implement deterministic next-run calculation and rescheduling helpers.

7. Add unit tests covering:
   - workflow CRUD
   - invalid workflow marking
   - next-run computation for each supported mode
   - timezone-aware scheduling behavior

### Acceptance Criteria

- Workflow definitions persist across service restarts.
- Invalid definitions are visible as invalid rather than silently disappearing.
- Next-run calculation is deterministic and test-covered for all supported
  schedule kinds.

## Milestone 3: Run Queue And Task Execution Bridge

### Deliverables

- persisted run queue
- executor claiming logic
- task execution bridge that reuses `task.py + task runtime`
- run-event recording
- retry policy support

### Tasks

1. Implement queue insertion for manual and scheduled runs.
   New runs must be persisted before execution begins.

2. Implement executor claiming logic with conservative concurrency defaults.
   First-version rule:
   - same workflow defaults to one active run at a time

3. Implement a workflow execution context that resolves:
   - task path
   - task metadata path
   - input overrides
   - output paths for the current run
   - workflow identity for logs and reporting

4. Reuse the existing task runner path where possible, but adapt it so workflow
   service execution can:
   - write run-scoped logs
   - capture status transitions
   - persist result JSON and artifact locations

5. Standardize run-event recording around meaningful milestones.
   Minimum events:
   - queued
   - claimed
   - task started
   - browser daemon ready or unavailable
   - task succeeded
   - task failed

6. Implement first-version retry behavior using:
   - `retry_attempts`
   - `retry_backoff_seconds`

7. Add tests for:
   - manual run queueing
   - executor claiming
   - success-path status transitions
   - failure-path status transitions
   - retry scheduling
   - browser daemon unavailable failure capture

### Acceptance Criteria

- Runs are visible in history before execution starts.
- Workflow execution still routes through existing task runtime contracts.
- Failures are attached to a run record with durable diagnostics.
- Retry behavior is deterministic and bounded.

## Milestone 4: Local API And Service Lifecycle

### Deliverables

- local-only workflow-service HTTP API
- status endpoint
- workflow CRUD endpoints
- run and retry endpoints
- lifecycle hooks for starting and stopping the service

### Tasks

1. Choose the lightest acceptable local HTTP serving approach and implement it.
   Recommendation:
   - prefer a minimal local-only Python HTTP stack over a large framework unless
     routing or lifecycle complexity proves that too costly

2. Implement local API endpoints:
   - `GET /api/service/status`
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

3. Ensure API responses are explicit about:
   - workflow validity
   - current enable/disable state
   - next run
   - latest run result
   - browser-daemon reachability when relevant

4. Add lifecycle behavior so the workflow service can be started and stopped
   predictably from Browser CLI-managed commands.

5. Add API tests for:
   - workflow CRUD
   - state toggling
   - run-now trigger
   - retry trigger
   - status endpoint

### Acceptance Criteria

- A local client can fully manage workflows without reading manifest files
  directly.
- Service lifecycle is controllable and testable.
- API errors clearly separate invalid workflow definitions from transient run
  failures.

## Milestone 5: Web UI Management Surface

### Deliverables

- local Web UI shell
- workflow list view
- workflow detail/edit view
- run history view
- run detail view

### Tasks

1. Build a minimal local Web UI that talks only to the workflow-service API.

2. Implement the workflow list view with:
   - name
   - enabled state
   - schedule summary
   - latest run status
   - next run
   - `Run now`

3. Implement the workflow detail/edit view with:
   - task path
   - metadata path
   - entrypoint
   - parameter overrides editor
   - schedule editor
   - output path editor
   - timeout and retry fields
   - enable/disable control

4. Implement run history view with:
   - trigger type
   - timestamps
   - status
   - error summary
   - retry action

5. Implement run detail view with:
   - event timeline
   - logs or structured event output
   - result path
   - artifact path
   - failure details

6. Add focused UI integration coverage for the critical management flow:
   - create or import
   - edit
   - enable
   - run now
   - inspect failed run
   - retry failed run

### Acceptance Criteria

- The Web UI is sufficient for day-to-day workflow management without falling
  back to CLI commands.
- Parameter editing is simple but functional without schema-generated forms.
- Failed runs are inspectable from the UI without reading raw DB records.

## Milestone 6: Import/Export, CLI Diagnostics, And Examples

### Deliverables

- `workflow.toml` import/export support
- minimal CLI diagnostics for workflow service
- at least two published task examples

### Tasks

1. Define the import path from `workflow.toml` into persisted workflow records.
   Import must validate:
   - manifest shape
   - referenced task metadata
   - schedule compatibility with supported modes

2. Define the export path from persisted workflow records back to
   `workflow.toml`.
   Export should include:
   - workflow identity
   - task binding
   - inputs
   - supported schedule fields
   - outputs
   - runtime policy

3. Add minimal CLI diagnostics and service commands.
   Candidate surfaces:
   - workflow-service status
   - workflow-service reload
   - workflow import/export helpers

4. Update or add at least two concrete task examples demonstrating:
   - one manual workflow
   - one recurring workflow

5. Add tests covering:
   - import validation
   - export round-trip stability for supported fields
   - CLI service-status output shape

### Acceptance Criteria

- `workflow.toml` remains useful as a portable publish contract.
- CLI can diagnose workflow-service state without becoming the primary UI.
- At least two tasks are demonstrably publishable under the new model.

## Milestone 7: Hardening, Docs Sync, And End-To-End Verification

### Deliverables

- end-to-end scheduled-run verification
- updated docs and examples
- guard coverage where architecture or product contracts changed
- final lint and guard cleanliness

### Tasks

1. Add integration tests proving:
   - persisted workflows survive service restart
   - scheduled runs are enqueued and executed
   - run history updates after success and failure
   - browser daemon failure becomes a durable run failure rather than silent
     loss

2. Update docs that describe workflow behavior and task/workflow relationships.
   Likely files include:
   - `AGENTS.md`
   - `docs/examples/task-and-workflow.md`
   - any workflow-specific docs that still describe `workflow` as one-shot only

3. Update guard expectations if architectural boundaries or public product
   contracts are changed.

4. Run repository validation after each code-change batch:
   - `scripts/lint.sh`
   - `scripts/guard.sh`
   - or `scripts/check.sh`

5. Perform at least one local smoke validation with a real published recurring
   workflow.

### Acceptance Criteria

- The workflow-service model is reflected in docs and guards.
- End-to-end scheduled execution is reproducible.
- Repository lint and guard checks pass at the end of the implementation.

## Suggested Implementation Order Inside Milestones

To reduce churn, follow this finer-grained order:

1. runtime paths and service status model
2. DB schema and persistence repository
3. schedule validation and next-run logic
4. queued-run creation and executor claiming
5. task execution bridge and run-event logging
6. local API
7. minimal Web UI shell
8. import/export helpers
9. CLI diagnostics
10. docs, examples, and end-to-end verification

## Risks And Control Measures

### Risk: Workflow service starts duplicating browser-daemon behavior

Control:

- keep browser actions and browser lifecycle inside existing daemon packages
- force workflow execution through task runtime instead of new browser helpers

### Risk: Manifest files and DB drift into dual sources of truth

Control:

- treat SQLite as runtime truth
- treat `workflow.toml` only as import/export and review artifact
- avoid features that write live scheduler state back into manifests

### Risk: First-version scheduling becomes too ambitious

Control:

- limit schedule modes to manual, interval, daily, and weekly
- defer full cron support

### Risk: UI scope expands faster than service stability

Control:

- implement only the four approved views
- keep UI thin over the local API

### Risk: Background runs become opaque to diagnose

Control:

- persist run records before execution
- store event timelines and run-scoped logs
- keep CLI diagnostics focused on workflow-service and browser-daemon health

## Done Criteria

This implementation is done when all of the following are true:

- the local workflow service persists workflow definitions and run history
- the Web UI can manage workflows end-to-end
- scheduled execution works for at least one recurring real task
- manual runs, failed runs, and retries are visible and diagnosable
- execution still depends on `task.py + task runtime + browser daemon`
- docs, examples, and guards reflect the new workflow-service model
