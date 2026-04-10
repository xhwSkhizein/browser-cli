# Browser CLI Dual-Driver Extension Architecture Implementation Plan

Date: 2026-04-10
Status: Ready for implementation
Related spec:

- `/Users/hongv/workspace/m-projects/browser-cli/docs/superpowers/specs/2026-04-10-browser-cli-dual-driver-extension-architecture-design.md`

## Planning Note

The expected `writing-plans` skill was not available in the current
environment. This document is the direct planning fallback and serves the same
purpose: an implementation-ready sequence for the approved dual-driver
extension architecture.

## Objective

Deliver a daemon-centric dual-driver runtime for `browser-cli` that preserves
current product semantics while adding a preferred real-Chrome extension
backend.

The final architecture should satisfy these approved requirements:

- `playwright_driver` remains the default managed-profile backend
- `extension_driver` becomes the preferred backend when a compatible extension
  is available
- daemon remains the only owner of tabs, `X_AGENT_ID`, active tab, busy-state,
  semantic refs, JSON contract, and rebinding policy
- the extension lives in the same repository and is developed first as an
  unpacked extension
- transport is a daemon-owned WebSocket connection initiated by the extension
- extension mode manages only Browser CLI's dedicated workspace window and tab
  set
- semantic ref generation and resolution remain daemon-owned and unified across
  both drivers
- automatic rebinding is allowed only at safe idle points and always surfaces
  `state_reset`
- extension mode must reach practical parity for the current public core
  actions:
  - `open`
  - `tabs`
  - `html`
  - `snapshot`
  - `click`
  - `fill`
  - `select`
  - `check`
  - `scroll`
  - `eval`
  - `wait`
  - `network`
  - `console`
  - `cookies`
  - `storage`
  - `verify`

## Out of Scope

The following are intentionally excluded from this plan:

- controlling arbitrary user browsing tabs outside the Browser CLI workspace
  window
- preserving complete runtime continuity across driver rebinding
- making Playwright and extension produce byte-identical snapshots or ref
  strings
- replacing WebSocket transport with Native Messaging
- first-pass parity for `trace`, `video`, or `pdf`
- a separate extension-specific CLI contract

## Delivery Strategy

Build the work in eight milestones:

1. driver abstraction and daemon integration
2. managed-profile backend alignment
3. extension transport and workspace bootstrap
4. extension driver core page execution
5. unified semantic-ref snapshot input
6. core action parity
7. safe-point rebinding and degraded-state handling
8. guards, docs, and acceptance coverage

The order matters. The extension should not grow its own ref system or action
contract; daemon-owned semantics must be preserved from the start.

## Design Constraints To Preserve

Implementation must preserve these approved decisions:

- daemon remains the single product control plane
- driver logic is capability-oriented, not backend-object-oriented
- drivers never accept `ref` directly
- drivers never return final formatted snapshot trees directly
- `playwright_driver` uses Browser CLI's managed profile domain
- `extension_driver` uses the user's real Chrome profile domain
- driver rebinding is allowed, but only at safe idle points
- any rebind across storage domains is explicitly treated as `state_reset`
- extension mode uses one Browser CLI workspace window
- only tabs in that workspace window are managed

## Repository Impact

Expected new or expanded repo areas:

```text
src/browser_cli/
  daemon/
  drivers/
  extension/
  refs/
  tabs/
browser-cli-extension/
  src/
  manifest.json
tests/
  unit/
  integration/
docs/
  superpowers/specs/
  superpowers/plans/
```

The extension is maintained in the same repository, not as a separate package
or repository.

## Milestone 1: Driver Abstraction And Daemon Integration

### Deliverables

- formal driver interface
- Playwright implementation moved behind the new interface
- daemon boot path updated to choose a driver instead of talking directly to
  Playwright session code

### Tasks

1. Create `src/browser_cli/drivers/` with at least:
   - `base.py`
   - `playwright_driver.py`
   - `models.py`

2. Define a capability-oriented driver interface covering:
   - workspace window lifecycle
   - tab lifecycle
   - page execution
   - raw snapshot input capture
   - low-level interaction
   - console, network, cookies, storage, and verify support

3. Refactor the current Playwright-backed browser code behind
   `playwright_driver` without changing daemon JSON contract.

4. Update daemon startup and runtime wiring so command handlers depend on a
   driver instance rather than concrete Playwright session objects.

5. Preserve current busy-state, `X_AGENT_ID`, and tab registry behavior while
   introducing the new abstraction.

### Acceptance Criteria

- all existing daemon-backed commands run through `playwright_driver`
- no public CLI contract changes
- new driver interface is test-covered and used in daemon boot

## Milestone 2: Managed-Profile Backend Alignment

### Deliverables

- managed profile becomes the explicit default backend profile domain
- current real-Chrome-profile probing is removed from the default runtime path
- daemon and `read` remain aligned with the managed-profile model

### Tasks

1. Make the managed Browser CLI profile the only default data directory used by
   `playwright_driver`.

2. Remove any remaining assumption that the default runtime path should attach
   directly to the user's primary Chrome data directory.

3. Ensure daemon-backed `read` continues to operate correctly under the managed
   profile backend.

4. Update docs and guard rules so the default backend assumption is explicit.

### Acceptance Criteria

- default daemon startup no longer depends on the user's primary Chrome profile
- `read` and daemon-backed actions remain functional under the managed profile
- docs and guards reflect the new default backend contract

## Milestone 3: Extension Transport And Workspace Bootstrap

### Deliverables

- repository-local unpacked extension scaffold
- daemon-owned WebSocket transport
- extension handshake and capability negotiation
- workspace-window discovery or creation

### Tasks

1. Add a repository-local extension directory, for example:
   - `browser-cli-extension/src/`
   - `browser-cli-extension/manifest.json`

2. Internalize the useful parts of `cdp-bridge-extension` into the new
   repository-local extension while keeping Browser CLI's ownership model.

3. Create `src/browser_cli/extension/` with at least:
   - `transport.py`
   - `protocol.py`
   - `session.py`

4. Implement daemon-side WebSocket endpoint and extension handshake.

5. Define handshake payload fields:
   - `protocol_version`
   - `extension_version`
   - `browser_name`
   - `browser_version`
   - `capabilities`
   - `workspace_window_state`
   - `extension_instance_id`

6. Add startup-time driver selection:
   - wait briefly for extension
   - choose `extension_driver` if compatible
   - otherwise choose `playwright_driver`

7. Implement extension-side workspace-window bootstrap so Browser CLI manages a
   dedicated workspace window only.

### Acceptance Criteria

- daemon can accept and validate an extension connection
- daemon can choose `extension_driver` at startup when a compatible extension is
  present
- extension can create or locate the dedicated Browser CLI workspace window

## Milestone 4: Extension Driver Core Page Execution

### Deliverables

- `extension_driver` skeleton
- tab lifecycle support in the workspace window
- navigation, evaluation, waiting, and HTML capture

### Tasks

1. Add `src/browser_cli/drivers/extension_driver.py`.

2. Implement extension-backed tab lifecycle:
   - list workspace tabs
   - open workspace tab
   - close workspace tab
   - activate workspace tab
   - report active workspace tab

3. Implement extension-backed page execution:
   - navigate
   - evaluate JavaScript
   - wait primitives
   - capture HTML

4. Normalize extension return values to the existing daemon-side JSON contract.

5. Add driver contract tests that run against both Playwright and extension for
   the implemented capabilities.

### Acceptance Criteria

- extension-backed open, tabs, eval, wait, and html work through the daemon
- daemon contract remains stable across both backends
- shared driver contract tests pass for these primitives

## Milestone 5: Unified Semantic-Ref Snapshot Input

### Deliverables

- a canonical driver-facing `SnapshotInput`
- Playwright snapshot-input adapter
- extension snapshot-input adapter
- daemon-side semantic-ref generation preserved as the only truth

### Tasks

1. Define a canonical `SnapshotInput` model that includes:
   - page and frame tree
   - parent-child relationships
   - sibling order
   - `role`
   - `name`
   - `text`
   - `tag`
   - `interactive`
   - `visible`
   - `enabled`
   - `checked`
   - `selected`
   - form semantics
   - `frame_path`
   - debug locator recipe

2. Make `playwright_driver.capture_snapshot_input()` return this shape.

3. Upgrade the extension so it no longer depends on temporary DOM-marker refs as
   its only interaction basis.

4. Make `extension_driver.capture_snapshot_input()` return the same shape.

5. Adapt daemon-side `browser_cli.refs` to consume the unified input while
   preserving existing semantic-ref generation rules.

### Acceptance Criteria

- both drivers produce the same logical `SnapshotInput` contract
- daemon-side ref generation remains backend-independent
- extension snapshot support is sufficient for semantic-ref reconstruction

## Milestone 6: Core Action Parity

### Deliverables

- extension-backed support for all approved core actions
- parity-focused tests across both drivers

### Tasks

1. Implement extension-backed versions of:
   - `click`
   - `fill`
   - `select`
   - `check`
   - `scroll`
   - `network`
   - `console`
   - `cookies`
   - `storage`
   - `verify`

2. Ensure ref-based actions still flow through daemon-owned semantic ref
   resolution and driver-level `locator_spec`, not through backend-specific ref
   logic.

3. Add parity fixtures and integration coverage for:
   - form controls
   - re-render after interaction
   - scrolling and lazy loading
   - console and network observation
   - cookies and storage inspection
   - verification flows

4. Mark `trace`, `video`, and `pdf` as explicitly unsupported-in-v1 where
   needed so behavior remains honest.

### Acceptance Criteria

- all current public core actions behave successfully under both drivers
- parity tests validate behavior, not backend-specific internal details
- no public core action depends on extension-local semantic-ref behavior

## Milestone 7: Safe-Point Rebinding And Degraded-State Handling

### Deliverables

- automatic downgrade from extension to Playwright at safe idle points
- automatic upgrade from Playwright to extension at safe idle points
- explicit `state_reset` semantics
- degraded state when rebinding cannot occur immediately

### Tasks

1. Add daemon runtime state for:
   - current driver
   - pending rebind request
   - degraded reason
   - last `state_reset`

2. Implement extension disconnect detection and schedule downgrade to
   `playwright_driver` at the next safe idle point.

3. Implement extension connect or reconnect detection and schedule upgrade to
   `extension_driver` at the next safe idle point.

4. On rebind:
   - rebuild Browser CLI workspace window ownership
   - rebuild logical tabs by reopening URLs where possible
   - invalidate snapshot registries and refs
   - clear or recreate console/network subscriptions

5. Surface machine-readable rebind metadata in command responses or daemon
   status.

6. Ensure rebinding never happens mid-command.

### Acceptance Criteria

- daemon automatically downgrades when extension disappears
- daemon automatically upgrades when extension becomes available again
- rebinding occurs only at safe idle points
- `state_reset` is explicit and test-covered

## Milestone 8: Guards, Docs, And Acceptance Coverage

### Deliverables

- updated lint and guard rules
- updated `AGENTS.md` and product docs
- explicit parity and real-Chrome smoke checklists

### Tasks

1. Update guard scripts so architecture drift is caught, including:
   - daemon remains the semantic-ref owner
   - drivers do not accept raw refs
   - drivers do not emit final snapshot formatting
   - extension mode remains workspace-window-only

2. Update `AGENTS.md` to document:
   - dual-driver architecture
   - managed profile default
   - extension preferred mode
   - rebinding semantics
   - testing and guard expectations

3. Update `README.md` and smoke docs for:
   - unpacked extension setup
   - extension handshake expectations
   - how to tell which driver is active
   - what `state_reset` means

4. Add or expand parity suites and smoke scripts for both drivers.

5. Ensure `scripts/guard.sh`, `scripts/lint.sh`, and `scripts/check.sh` cover
   the new driver and extension architecture.

### Acceptance Criteria

- architecture guards encode the approved constraints
- docs explain the dual-driver system clearly
- the standard validation entrypoints cover the new architecture

## Recommended Slice Order

Implement in these slices:

1. introduce `drivers/` and move current Playwright path behind it
2. lock managed profile as the default backend domain
3. land daemon-side extension transport and handshake
4. add repo-local unpacked extension shell
5. make extension control workspace window and tabs
6. implement extension eval, wait, and html
7. define and adopt canonical `SnapshotInput`
8. move extension snapshot to unified input
9. implement remaining core actions under extension driver
10. add safe-point rebinding and degraded-state handling
11. expand guards, docs, and parity tests

This order keeps Browser CLI working throughout the migration and avoids a
flag-day rewrite.

## Verification Matrix

Before calling the work complete, verify all of the following:

- `playwright_driver` still passes existing managed-profile flows
- extension can connect and become the active backend at daemon startup
- extension absence falls back cleanly to Playwright
- extension reconnect can trigger automatic safe-point upgrade
- core public actions pass under both drivers
- semantic-ref generation remains daemon-owned
- old refs are invalid after driver rebind
- workspace-window isolation holds
- guards and lint pass

## Final Recommendation

Implement the dual-driver architecture as a daemon-owned evolution of the
current Browser CLI runtime, not as an extension-led rewrite.

The critical success criterion is not merely "extension mode can control a real
Chrome tab". It is:

- one product contract
- one semantic-ref system
- one daemon-owned state model
- two interchangeable browser backends

Everything in this plan should be judged against that constraint.
