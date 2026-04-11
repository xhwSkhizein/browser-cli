# Browser CLI Status And Reload Implementation Plan

Date: 2026-04-10
Status: Ready for implementation
Related spec:

- `/Users/hongv/workspace/m-projects/browser-cli/docs/superpowers/specs/2026-04-10-browser-cli-status-reload-design.md`

## Planning Note

The expected `writing-plans` skill was not available in the current
environment. This document is the direct planning fallback and serves the same
purpose: an implementation-ready sequence for the approved `status` and
`reload` lifecycle commands.

## Objective

Add two top-level lifecycle commands to `browser-cli`:

- `browser-cli status`
- `browser-cli reload`

The final implementation should satisfy these approved requirements:

- `status` is a human-readable top-level diagnosis command
- `status` works both when the daemon is stopped and when it is live
- `status` aggregates local runtime facts and live daemon diagnostics
- `reload` is a top-level runtime reset command, distinct from page action
  `reload`
- `reload` only affects Browser CLI-owned workspace/tabs
- `reload` succeeds if Browser CLI returns to a usable managed-profile
  baseline, even if extension mode is not yet connected
- lifecycle docs and guards are updated so diagnosis and reset behavior remain
  stable over time

## Out Of Scope

The following are intentionally excluded:

- any replacement of the existing page reload action semantics
- any attempt to close arbitrary user Chrome tabs or windows
- adding a broader operator suite such as `doctor` or `restart --hard`
- first-pass JSON output for `status`
- changing the existing action catalog contract

## Delivery Strategy

Build the work in five milestones:

1. daemon runtime-status diagnostics
2. top-level `status` command and formatter
3. top-level `reload` lifecycle orchestration
4. tests for stopped, broken, degraded, and healthy states
5. docs and guard updates

This order keeps runtime truth in one place first, then builds the user-facing
commands on top of it.

## Design Constraints To Preserve

Implementation must preserve these approved decisions:

- `status` and top-level `reload` are lifecycle commands, not action-catalog
  commands
- daemon remains the authoritative owner of live runtime facts
- page action `reload` remains unchanged
- `reload` only resets Browser CLI runtime and Browser CLI workspace state
- extension absence after restart is a degraded-but-usable outcome, not an
  automatic `reload` failure
- docs and guards must explicitly preserve the new lifecycle surface

## Repository Impact

Expected touched areas:

```text
src/browser_cli/
  cli/
  commands/
  daemon/
scripts/guards/
tests/
  unit/
  integration/
docs/
  superpowers/specs/
  superpowers/plans/
README.md
AGENTS.md
docs/smoke-checklist.md
```

Suggested new modules:

- `src/browser_cli/commands/status.py`
- `src/browser_cli/commands/reload.py`

## Milestone 1: Daemon Runtime-Status Diagnostics

### Deliverables

- internal daemon diagnostic action
- structured runtime-status payload
- client helper to query runtime-status without polluting public action catalog

### Tasks

1. Add a read-only daemon action such as `runtime-status`.
2. Surface daemon-owned runtime facts including:
   - package/runtime version
   - daemon pid and start time
   - active driver
   - driver health
   - extension connection and capability state
   - workspace window state
   - visible tab summary
   - busy tab count
   - active tab summary
   - profile source
   - pending rebind state
3. Keep this action internal to lifecycle commands rather than exposing it as a
   normal user-facing action command.
4. Add a client helper for lifecycle commands to query this payload when the
   daemon is reachable.

### Acceptance Criteria

- daemon can return a structured runtime-status payload
- runtime-status reflects the currently active driver and workspace state
- no new public action-catalog command is introduced

## Milestone 2: Top-Level `status` Command

### Deliverables

- CLI parser support for `browser-cli status`
- local runtime inspection layer
- human-readable formatter with guidance

### Tasks

1. Add top-level `status` parser wiring in `browser_cli.cli.main`.
2. Create `browser_cli.commands.status` to orchestrate:
   - local path inspection
   - run-info inspection
   - socket reachability
   - runtime compatibility check
   - optional live daemon runtime-status fetch
3. Implement runtime classification:
   - `stopped`
   - `broken`
   - `degraded`
   - `healthy`
4. Implement stable human-readable sections:
   - summary
   - runtime
   - daemon
   - backend
   - browser
   - guidance
5. Ensure `status` is non-mutating and works without any active page.

### Acceptance Criteria

- `browser-cli status` works when the daemon is stopped
- `browser-cli status` works when the daemon is live
- output includes short next-step guidance based on detected state

## Milestone 3: Top-Level `reload` Command

### Deliverables

- CLI parser support for `browser-cli reload`
- lifecycle orchestration for graceful stop, forced cleanup, restart, and
  status summary

### Tasks

1. Add top-level `reload` parser wiring in `browser_cli.cli.main`.
2. Create `browser_cli.commands.reload` to orchestrate:
   - small `before` lifecycle snapshot
   - graceful daemon stop if reachable
   - forced cleanup of stale runtime state for the current
     `BROWSER_CLI_HOME` if needed
   - daemon restart using existing client lifecycle helpers
   - fresh `after` status snapshot
3. Reuse existing client cleanup and spawn helpers rather than implementing a
   second lifecycle mechanism.
4. Make result reporting explicit about:
   - whether graceful stop succeeded
   - whether forced cleanup was needed
   - which backend is active after restart
   - whether the resulting state is healthy or degraded
5. Ensure `reload` never targets arbitrary user tabs and only resets Browser
   CLI-owned workspace/runtime state.

### Acceptance Criteria

- `browser-cli reload` succeeds with no live daemon
- `browser-cli reload` succeeds with a live compatible daemon
- `browser-cli reload` can recover from stale runtime state
- `reload` reports degraded success when managed backend is usable but extension
  is absent

## Milestone 4: Tests

### Deliverables

- unit coverage for lifecycle classification and orchestration
- integration coverage for restart and post-restart usability

### Tasks

1. Add unit tests for `status`:
   - stopped daemon
   - stale run-info with unreachable socket
   - live compatible daemon
   - degraded managed-backend state
   - guidance string selection
2. Add unit tests for `reload`:
   - no daemon present
   - graceful stop path
   - forced cleanup path
   - restart failure reporting
3. Add integration tests for:
   - `reload` followed by successful `open`
   - `status` reflecting managed profile and active driver
   - extension absent but managed backend usable
4. Add output stability assertions for the main human-readable sections without
   freezing every exact line.

### Acceptance Criteria

- lifecycle command tests cover stopped, broken, degraded, and healthy states
- `reload` integration proves the runtime is usable again after reset

## Milestone 5: Docs And Guards

### Deliverables

- README lifecycle documentation
- AGENTS maintenance rules
- smoke-checklist troubleshooting updates
- guard rules preserving lifecycle command placement

### Tasks

1. Update `README.md` with:
   - when to use `status`
   - when to use `reload`
   - what `reload` does and does not reset
2. Update `AGENTS.md` with:
   - lifecycle command expectations
   - required post-change verification using `./scripts/check.sh`
   - guidance to run `browser-cli status` first when diagnosing runtime issues
3. Update `docs/smoke-checklist.md` with:
   - lifecycle troubleshooting flow
   - extension-degraded expectations
4. Update guard scripts so they assert:
   - `status` exists as a top-level command
   - top-level `reload` exists as a lifecycle command
   - neither command is folded into the public action catalog

### Acceptance Criteria

- lifecycle commands are documented in README and AGENTS
- guard coverage protects the approved command placement and product shape

## Recommended Implementation Slices

Implement in these slices to keep reviewable progress:

1. daemon runtime-status payload and client query helper
2. `status` parser + formatter + unit tests
3. `reload` parser + orchestration + unit tests
4. integration tests for reset and degraded fallback
5. docs and guard updates

## Verification Checklist

Before closing the implementation, run:

- `./scripts/guard.sh`
- `./scripts/lint.sh`
- targeted lifecycle command tests
- at least one manual check:
  - `browser-cli status`
  - `browser-cli reload`
  - `browser-cli status`

Expected end state:

- `status` gives a clear diagnosis and next-step guidance
- `reload` returns Browser CLI to a usable state without touching arbitrary
  user tabs
- docs and guards keep the lifecycle contract stable
