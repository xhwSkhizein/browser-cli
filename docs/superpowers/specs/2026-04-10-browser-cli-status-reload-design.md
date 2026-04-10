# Browser CLI Status And Reload Design

Date: 2026-04-10
Status: Drafted for review
Repo: `/Users/hongv/workspace/m-projects/browser-cli`

## Summary

`browser-cli` should add two top-level lifecycle commands:

- `browser-cli status`
- `browser-cli reload`

These commands are not page actions. They are runtime management commands for
the Browser CLI daemon, driver state, extension connectivity, and Browser CLI's
own workspace window and tabs.

`status` should provide a human-readable diagnosis surface for both users and
agents. It should make the current runtime legible and provide short next-step
guidance when the system is degraded.

`reload` should provide a deterministic "reset Browser CLI to a clean usable
state" path. It must only affect Browser CLI's own runtime and workspace tabs.
It must never close or mutate arbitrary user browsing tabs.

## Problem Statement

Browser CLI now has a richer runtime than the original single-browser model:

- daemon run-info and socket lifecycle
- managed Playwright backend
- extension-backed real-Chrome backend
- automatic rebinding between drivers
- Browser CLI-owned workspace window and tabs

When something goes wrong, the current CLI does not expose a single clear place
to answer:

- is the daemon running
- is the socket healthy
- which driver is active
- is the extension connected
- is the system degraded or broken
- what should the user do next

At the same time, the current recovery path is fragmented. The user can stop
the daemon, but there is no single top-level command that:

- clears stale Browser CLI runtime state
- restarts the daemon and browser backend
- resets Browser CLI-owned workspace state
- returns the system to a known-good baseline

## Goals

- Add a top-level `status` command with human-readable output.
- Make `status` useful for both humans and agents.
- Aggregate local runtime state and live daemon state into one view.
- Add a top-level `reload` command for runtime reset and restart.
- Restrict `reload` to Browser CLI-owned workspace/tabs only.
- Keep the existing daemon JSON action contract unchanged.
- Preserve the current action catalog and page-level `reload`.
- Add clear operational guidance to docs and maintenance rules.

## Non-Goals

- No replacement of existing page-level `reload` action.
- No conversion of `status` into a normal daemon action command.
- No attempt to close arbitrary user-visible Chrome tabs outside Browser CLI's
  managed workspace.
- No requirement that `reload` waits for extension mode to become active before
  succeeding.
- No new general-purpose `doctor` or `restart --hard` command family in this
  iteration.

## Options Considered

### 1. Minimal wrappers

Add a lightweight `status` that only reads local files, and a lightweight
`reload` that only runs `stop` then triggers daemon startup.

Advantages:

- smallest change
- little new code

Disadvantages:

- weak diagnostics
- poor handling for stale or partially broken runtime state
- unclear guidance in degraded situations

Rejected.

### 2. Top-level lifecycle commands

Add explicit top-level commands:

- `status`
- `reload`

`status` combines local runtime inspection with live daemon diagnostics.
`reload` performs controlled runtime reset and restart, then reports the new
state.

Advantages:

- directly matches the operational need
- keeps lifecycle concerns separate from page actions
- gives one obvious diagnosis path and one obvious reset path

Disadvantages:

- requires a new daemon diagnostic surface
- requires lifecycle orchestration in the CLI layer

Chosen direction.

### 3. Larger operator command suite

Add `status`, `reload`, `doctor`, `restart --hard`, and verbose diagnostics in
one iteration.

Advantages:

- comprehensive operations surface

Disadvantages:

- too much surface area for the current need
- would add policy and complexity before the core contract is proven

Rejected.

## Chosen Direction

Browser CLI should add a pair of top-level lifecycle commands:

- `browser-cli status`
- `browser-cli reload`

These commands live beside `read`, `workflow`, and the action catalog, but they
are not part of the action catalog.

The split of responsibility should be:

- CLI `status`: local runtime inspection + live daemon query + human-readable
  output formatting
- daemon diagnostic endpoint: authoritative runtime facts about the live daemon
- CLI `reload`: reset orchestration and final reporting

## Command Surface

### `browser-cli status`

Purpose:

- inspect current Browser CLI runtime state
- explain whether the runtime is healthy, degraded, or broken
- provide concise operational guidance

Characteristics:

- must work even when daemon is not running
- must not require any active page
- must not mutate runtime state
- default output is human-readable text

Future JSON output may be added later, but is not required for the first
iteration.

### `browser-cli reload`

Purpose:

- reset Browser CLI's runtime state
- clean up Browser CLI-owned workspace/tabs
- restart daemon and browser backend
- return the system to a known usable state

Characteristics:

- top-level lifecycle command, not page action
- may perform forced cleanup if graceful shutdown fails
- succeeds if Browser CLI returns to a usable managed-profile baseline
- does not require extension mode to be connected at completion

## Architecture

### CLI Layer

`status` and `reload` should be added in:

- `browser_cli.cli.main`
- dedicated command modules under `browser_cli.commands`

Suggested modules:

- `browser_cli.commands.status`
- `browser_cli.commands.reload`

These modules should stay orchestration-focused and not own low-level process
or socket logic.

### Daemon Diagnostic Endpoint

The live daemon should expose a read-only diagnostic action, for example:

- `runtime-status`

This action is internal to the CLI lifecycle commands. It is not part of the
public action catalog shown to end users.

The endpoint should surface:

- daemon package/runtime version
- active driver
- driver health
- extension connection and capability state
- workspace window state
- tab summary
- profile source
- pending rebind state

### Client Lifecycle Helpers

Existing daemon client lifecycle helpers should remain the basis for restart
behavior:

- socket probing
- stale runtime cleanup
- process-tree termination
- daemon startup and compatibility checks

`reload` should orchestrate these helpers more explicitly, but should not create
a parallel lifecycle implementation.

## Status Data Model

`status` should combine two layers of information.

### Local Runtime Inspection

Available even when daemon is down:

- `BROWSER_CLI_HOME`
- run directory
- socket path
- run-info path
- daemon log path
- whether run-info exists
- whether socket path exists and responds
- whether recorded runtime version matches the current CLI

### Live Daemon Diagnostics

Available only when daemon is reachable:

- daemon pid and start time
- active driver
- driver health details
- extension hello metadata and capabilities
- workspace window state
- profile source
- visible tab count
- busy tab count
- active tab summary
- pending safe-point rebind

## Status Output Shape

The default human-readable output should use a stable section layout.

### Summary

One headline line:

- `Status: healthy`
- `Status: degraded`
- `Status: broken`
- `Status: stopped`

This line should be derived from runtime facts rather than from a single boolean
flag.

### Runtime

Show path and version information:

- home
- socket
- run-info
- daemon log
- package version
- runtime version

### Daemon

Show lifecycle and compatibility information:

- daemon state: stopped / running / stale / incompatible
- pid if available
- socket reachable: yes/no
- runtime compatibility: yes/no

### Backend

Show driver and extension information:

- active driver
- extension connected: yes/no
- extension capability complete: yes/no
- pending rebind: none / upgrade / downgrade

### Browser

Show Browser CLI workspace information:

- profile source
- workspace window present: yes/no
- workspace tab count
- active tab
- busy tab count

### Guidance

Show short next-step advice based on current state. Examples:

- daemon not running: open a page or run `browser-cli reload`
- runtime incompatible: run `browser-cli reload`
- extension disconnected: check popup status and `chrome://extensions`
- degraded on managed backend: Browser CLI is usable and will upgrade to
  extension mode at a safe idle point

The guidance section should remain short and prescriptive.

## Runtime Status Classification

Suggested classification rules:

- `stopped`
  - no reachable daemon
  - no obviously stale incompatible live process

- `broken`
  - run-info exists but socket is unreachable
  - or daemon is live but required runtime facts cannot be collected

- `degraded`
  - daemon is running and usable
  - but extension is absent or incomplete
  - or pending rebind exists
  - or Browser CLI is running on the managed fallback backend

- `healthy`
  - daemon is running
  - runtime is compatible
  - required driver health checks pass
  - no pending rebind
  - workspace state is internally consistent

## Reload Behavior

`browser-cli reload` should implement a hard runtime reset for Browser CLI's own
surface.

Execution order:

1. capture a small `before` lifecycle snapshot
2. attempt graceful daemon shutdown if the daemon is reachable
3. if graceful shutdown does not fully clear runtime state, perform forced
   cleanup for the current `BROWSER_CLI_HOME`
4. clear Browser CLI runtime artifacts for this home:
   - stale run-info
   - stale socket
   - current daemon process tree if still alive
5. restart daemon and browser backend
6. collect a fresh `status` snapshot
7. print a human-readable result with the new state summary

## Reload Scope

`reload` must only affect Browser CLI-owned runtime and workspace state.

Allowed effects:

- stop the current Browser CLI daemon
- close Browser CLI workspace window and tabs
- clear Browser CLI socket and run-info state
- restart Browser CLI daemon and backend

Forbidden effects:

- closing arbitrary user browsing tabs
- mutating unrelated Chrome windows
- clearing the user's general Chrome session

## Reload Success Criteria

`reload` should be considered successful if:

- stale runtime state is cleared
- a compatible daemon is running after restart
- Browser CLI can accept subsequent commands

Extension mode is preferred but not required for success. If the extension is
not connected after restart, Browser CLI should still succeed on the managed
backend and report a degraded but usable state.

## Reload Failure Semantics

### Graceful stop fails, forced cleanup succeeds

Result:

- `reload` succeeds
- output explicitly states `forced cleanup: yes`

### Restart fails after cleanup

Result:

- `reload` fails
- output explains that runtime reset completed but restart did not
- output includes next-step guidance using `daemon log` and `status`

### Extension does not reconnect after restart

Result:

- `reload` still succeeds if managed backend is usable
- status summary is `degraded`

## Interaction With Existing Commands

- Existing page action `reload` remains unchanged.
- Existing `stop` action remains available.
- `status` and top-level `reload` are new lifecycle commands, not replacements
  for action commands.
- `read`, `open`, and other existing commands should continue to work without
  requiring use of `status` or `reload`.

## Testing

### Unit Tests

Add coverage for:

- `status` when daemon is stopped
- `status` when run-info exists but socket is stale
- `status` when daemon is live and compatible
- `status` guidance selection
- `reload` with no live daemon
- `reload` with graceful stop
- `reload` with forced cleanup

### Integration Tests

Add coverage for:

- `reload` followed by successful `open`
- `status` reflecting active driver and managed profile state
- extension absent but managed backend usable

### Output Stability Tests

Add targeted assertions that the human-readable output includes:

- summary headline
- key runtime paths
- backend line
- guidance section

This is not to freeze every line of formatting, but to keep the operational
surface intact.

## Documentation And Guard Updates

The following docs should be updated when implemented:

- `README.md`
- `AGENTS.md`
- `docs/smoke-checklist.md`

Maintenance rules should explicitly state:

- run `./scripts/check.sh` after code changes
- use `browser-cli status` for first-line diagnosis
- use `browser-cli reload` when Browser CLI runtime state needs to be reset

Guard rules should assert:

- `status` remains a top-level lifecycle command
- top-level `reload` remains distinct from the action catalog
- architecture docs stay aligned with the lifecycle command surface

## Open Questions Resolved

- Default output format for `status`:
  human-readable text

- Scope of `reload`:
  only Browser CLI workspace/tabs, never arbitrary user tabs

- Post-reload success target:
  restarted, usable Browser CLI runtime even if extension is not yet connected

## Recommended Implementation Order

1. add daemon diagnostic action and client data model
2. add top-level `status` command and text formatter
3. add top-level `reload` command using existing lifecycle helpers
4. add tests for stopped, degraded, broken, and healthy states
5. update README, AGENTS, smoke checklist, and guards
