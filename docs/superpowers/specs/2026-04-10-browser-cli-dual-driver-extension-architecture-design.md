# Browser CLI Dual-Driver Extension Architecture Design

Date: 2026-04-10
Status: Drafted for review
Repo: `/Users/hongv/workspace/m-projects/browser-cli`

## Summary

`browser-cli` should evolve from a single Playwright-backed browser runtime into
a dual-driver daemon architecture:

- `managed profile mode`: default, stable, easy to test
- `extension mode`: advanced, real Chrome, requires an installed extension

The product contract remains the same:

- CLI still talks only to the daemon
- daemon still owns tabs, `X_AGENT_ID`, active tab, busy-state, and JSON output
- semantic refs remain a single daemon-owned system

The change is below that line:

- daemon chooses a browser driver
- `playwright_driver` remains the default fallback
- `extension_driver` becomes the preferred backend when a compatible extension
  connects

The first extension-backed version must reach practical parity with the current
managed profile mode for all public core actions:

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

`trace`, `video`, and `pdf` may remain follow-up work.

## Problem Statement

Browser CLI currently has two conflicting goals:

1. remain stable and testable through a managed browser profile
2. operate against a real user Chrome environment when needed

The current Playwright-persistent-launch model no longer satisfies both goals at
the same time.

Recent Chrome changes restrict remote debugging against the default Chrome data
directory, which breaks direct attachment to the user's primary Chrome profile
through the current path. At the same time, browser automation against a
dedicated managed profile is still valuable because it is isolated and easy to
test.

The system therefore needs:

- one stable default backend
- one real-Chrome backend
- one shared product contract above them

Without that split, Browser CLI will keep oscillating between:

- good testability but weak real-browser integration
- better real-browser access but growing architecture drift

## Goals

- Preserve the existing CLI and daemon product shape.
- Keep daemon-owned semantics as the single source of truth.
- Introduce a driver abstraction that supports both Playwright and extension
  backends.
- Prefer the extension backend when available, but retain a stable managed
  profile fallback.
- Keep semantic ref generation and resolution unified across both drivers.
- Support automatic driver rebinding at safe idle points.
- Reach extension-mode parity for all currently public core actions.
- Limit extension scope to Browser CLI's own dedicated workspace window and tab
  set.
- Keep the system maintainable in a single repository.

## Non-Goals

- No takeover of arbitrary user browsing tabs in the first extension-backed
  version.
- No attempt to preserve full runtime continuity across driver switches.
- No claim that extension and Playwright produce byte-identical snapshots or
  refs.
- No native-messaging transport in the first iteration.
- No replacement of daemon JSON contract with an extension-specific protocol.
- No requirement that `trace`, `video`, and `pdf` reach parity in the first
  extension milestone.

## Options Considered

### 1. Extension-heavy backend

The extension would own most browser semantics, including snapshot generation,
refs, and interaction logic, while the daemon mostly forwards commands.

Advantages:

- close to existing `opencli` and `cdp-bridge-extension` style
- faster to make basic real-Chrome control work

Disadvantages:

- creates two semantic systems
- causes drift between Playwright and extension behavior
- directly conflicts with the requirement for semantic-ref parity

Rejected.

### 2. Per-command backend switching

Daemon would choose between Playwright and extension on a command-by-command
basis.

Advantages:

- looks flexible
- can opportunistically use the best available backend per command

Disadvantages:

- breaks tab-state assumptions
- complicates busy-state, observability streams, and ref registry ownership
- makes driver behavior hard to reason about and test

Rejected.

### 3. Daemon-centric dual-driver architecture

Daemon keeps all product semantics; drivers only provide low-level browser
capabilities. Driver selection is daemon-owned. Extension is the preferred
backend when available, and Playwright remains the managed fallback.

Advantages:

- preserves one product contract
- preserves one semantic ref system
- contains backend complexity behind a stable interface
- best supports parity testing

Disadvantages:

- requires a larger internal refactor up front
- demands a more formal driver interface than the current codebase has

Chosen direction.

## Chosen Direction

Browser CLI should adopt a daemon-centric dual-driver architecture.

The daemon remains the product center of gravity. It continues to own:

- command handling
- tab registry
- `X_AGENT_ID` visibility
- active tab rules
- busy-state rules
- semantic ref generation and resolution
- JSON action contract

Browser backends become replaceable drivers:

- `playwright_driver`
- `extension_driver`

The extension backend is preferred, but it is not allowed to redefine Browser
CLI semantics. It is a low-level browser capability provider, not a second
product runtime.

## Product Shape

Externally, Browser CLI still looks the same:

```bash
browser-cli open https://example.com
browser-cli snapshot
browser-cli click @8d4b03a9
browser-cli html
browser-cli network
```

Internally, daemon startup changes from:

`start daemon -> start Playwright browser -> serve commands`

to:

`start daemon -> wait briefly for extension -> choose driver -> serve commands`

The user should not need a second CLI surface for extension mode. The daemon
selects the backend automatically.

## Backend Profile Domains

The two drivers intentionally bind different browser-storage domains:

- `playwright_driver` uses Browser CLI's managed profile
- `extension_driver` uses the user's real Chrome profile

This difference is fundamental to the design.

It is the reason automatic driver rebinding may rebuild logical tabs and restore
URLs, but must still be treated as `state reset` rather than as seamless
continuity.

## Module Boundaries

### `browser_cli.daemon`

Remains the only control center.

Responsibilities:

- CLI request handling
- JSON contract
- driver selection and lifecycle
- tab and visibility semantics
- busy-state and conflict rules
- semantic ref registry and resolver
- rebinding coordination

### `browser_cli.drivers`

New driver abstraction layer.

Suggested structure:

- `browser_cli.drivers.base`
- `browser_cli.drivers.playwright_driver`
- `browser_cli.drivers.extension_driver`

Responsibilities:

- manage Browser CLI workspace window and tabs
- navigate and evaluate
- collect raw page structure input
- execute low-level actions
- surface console, network, cookies, and storage data

Non-responsibilities:

- no daemon JSON response shaping
- no `X_AGENT_ID` logic
- no semantic ref generation
- no product-level busy-state policy

### `browser_cli.refs`

Remains the single semantic-ref truth layer.

Responsibilities:

- convert raw snapshot input into canonical `RefData`
- maintain per-tab ref registries
- resolve refs into driver-level locator specs
- return `STALE_REF`, `AMBIGUOUS_REF`, and `REF_NOT_FOUND` style errors

This layer must not split by driver.

### `browser_cli.tabs`

Continues to manage logical tab state:

- Browser CLI workspace window identity
- logical tabs
- active tab
- per-agent visibility
- busy ownership

### `browser_cli.extension`

New transport and session-management layer between daemon and extension.

Responsibilities:

- WebSocket server endpoint
- extension handshake
- capability negotiation
- heartbeat and disconnect detection
- extension session health

### Repository-local extension source

The extension should live in the same repository and be maintained alongside
Browser CLI runtime code.

Recommended layout:

```text
browser-cli-extension/
  src/
  manifest.json
```

The first development mode is unpacked Chrome extension loading.

## Driver Interface

The daemon should depend on a capability-oriented driver interface, not on
Playwright or Chrome-extension-native objects.

Suggested required interface groups:

### Browser and window

- `ensure_workspace_window()`
- `health()`
- `shutdown()`

### Tab lifecycle

- `list_tabs()`
- `open_tab(url)`
- `close_tab(tab_id)`
- `activate_tab(tab_id)`
- `get_active_tab()`

### Page execution

- `navigate(tab_id, url)`
- `eval(tab_id, expression, args)`
- `wait(tab_id, spec)`
- `capture_html(tab_id)`
- `capture_snapshot_input(tab_id)`

### Interaction

- `click(tab_id, locator_spec)`
- `fill(tab_id, locator_spec, value)`
- `select(tab_id, locator_spec, value)`
- `check(tab_id, locator_spec, checked)`
- `scroll(tab_id, spec)`

### Observability and state

- `get_console_events(tab_id)`
- `get_network_events(tab_id)`
- `get_cookies(tab_id, filter)`
- `get_storage(tab_id)`
- `verify(tab_id, spec)`

Two constraints are mandatory:

1. drivers do not accept `ref` directly
2. drivers do not return final snapshot trees directly

Refs stay daemon-owned. Snapshot formatting stays daemon-owned.

## Driver Selection and Rebinding

### Startup selection

Daemon startup should follow this flow:

1. start daemon process
2. open WebSocket endpoint for extension handshake
3. wait a short handshake window
4. if a compatible extension connects, choose `extension_driver`
5. otherwise choose `playwright_driver`

The handshake window should be short and bounded. A few seconds is sufficient.

### Handshake payload

The extension should provide:

- `protocol_version`
- `extension_version`
- `browser_name`
- `browser_version`
- `capabilities`
- `workspace_window_state`
- `extension_instance_id`

Daemon should record:

- chosen driver
- reason for selection
- capability gaps if any
- extension connectivity state

### Runtime rebinding

Unlike the earlier fixed-driver idea, Browser CLI should support automatic
driver rebinding at safe idle points.

Allowed transitions:

- `extension_driver -> playwright_driver`
- `playwright_driver -> extension_driver`

Rules:

- rebinding only occurs when daemon is idle or at another defined safe point
- rebinding never occurs mid-command
- if the daemon is busy, it enters a degraded pending-rebind state until the
  active command finishes

### Rebinding semantics

Rebinding is explicitly treated as `state reset`.

Daemon may rebuild:

- Browser CLI workspace window
- Browser CLI logical tabs
- tab URLs
- active-tab designation

Daemon must invalidate:

- old refs
- old snapshot registries
- old network and console subscriptions

Daemon must not pretend to preserve:

- full page runtime state
- form state
- JavaScript in-memory state
- session continuity across different profile domains

Commands that observe the rebinding should receive machine-readable metadata
indicating that a state reset occurred.

## Workspace Window and Tab Isolation

In extension mode, Browser CLI should manage a dedicated workspace window.

Rules:

- Browser CLI creates or reuses one dedicated workspace window
- Browser CLI manages only tabs inside that workspace window
- ordinary user browsing windows are out of scope
- extension mode does not control arbitrary visible tabs

This keeps:

- tab ownership clear
- active-tab semantics stable
- observability scoping tractable
- user trust higher

## Semantic Ref Unification

Semantic refs must remain daemon-owned and backend-independent.

### Unified `SnapshotInput`

Both drivers should produce a unified raw page-structure input that the daemon
then converts into canonical Browser CLI refs.

`SnapshotInput` should include at least:

- page and frame tree
- node parent-child relationships
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
- form-value semantics
- `frame_path`
- debug locator recipe

### Unified resolver

Daemon-side ref processing then remains consistent:

- generate `RefData`
- store tab-scoped ref registry
- resolve refs into driver-level `locator_spec`

This preserves one semantic-ref system across both drivers.

### Rebinding effect on refs

Within the same driver and page context, stale refs may be semantically
reconstructed.

Across driver rebinding:

- all previous refs are invalid
- a new snapshot is required

This is necessary because the backend, page state, and often storage domain may
have changed.

## Extension Backend Requirements

The repository-local extension should be evolved from the current
`cdp-bridge-extension` direction, but adapted to Browser CLI semantics.

It should be treated as a backend implementation, not as an independent product.

### Transport requirements

- daemon-directed WebSocket session
- heartbeat
- reconnect support
- capability reporting
- workspace-window discovery or creation

### Snapshot-input requirements

The extension must provide enough raw page structure for daemon-owned semantic
refs. The current DOM-marker-only approach is insufficient.

The extension therefore must expose richer data than:

- temporary DOM marker refs
- one-shot selector lookup

It must expose the unified `SnapshotInput` shape needed by daemon refs.

### Core action requirements

The first parity milestone must support:

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

These are not optional for the first extension milestone.

## Error Handling

Error handling should distinguish between:

- extension unavailable
- extension connected but capability-incomplete
- driver health failure
- pending rebind
- state reset after rebind
- stale semantic ref
- ambiguous semantic ref

Errors should remain machine-readable and should avoid silently switching
behavior without surfacing that a rebind occurred.

## Testing and Acceptance

This architecture should be accepted only through parity-focused tests, not by
manual spot checks alone.

### 1. Driver contract tests

Run the same contract suite against both drivers:

- tab lifecycle
- eval and wait
- html capture
- cookies and storage
- console and network
- interaction primitives

### 2. Semantic-ref parity tests

Use shared fixture pages and shared daemon-side ref generation to confirm that
the same logical steps succeed on both backends.

The goal is behavioral parity, not byte-identical ref strings.

### 3. Rebinding tests

Verify:

- startup waits briefly for extension
- daemon chooses Playwright when extension is absent
- daemon chooses extension when present
- extension disconnect triggers safe-point downgrade
- extension reconnect triggers safe-point upgrade
- `state_reset` is surfaced
- old refs become invalid after rebinding

### 4. Real-Chrome smoke tests

Manual smoke tests outside CI should verify:

- unpacked extension install
- daemon handshake
- dedicated workspace window creation
- core action success against the user's real Chrome profile

## Rollout Strategy

Recommended rollout order:

1. introduce driver abstraction behind the current Playwright implementation
2. add extension transport and handshake
3. add repository-local unpacked extension
4. make extension capable of tab lifecycle and raw page execution
5. upgrade extension snapshot input to support daemon-owned semantic refs
6. reach parity for all public core actions
7. add safe-point rebinding
8. expand guard and parity tests

This keeps Browser CLI usable throughout the migration instead of requiring a
flag day rewrite.

## Final Recommendation

Browser CLI should keep its current daemon-centric product model and add a
dual-driver backend architecture.

`playwright_driver` remains the stable managed-profile backend.
`extension_driver` becomes the preferred real-Chrome backend when available.

The daemon remains the single owner of:

- tabs
- `X_AGENT_ID`
- semantic refs
- JSON contract
- busy-state
- rebinding policy

The extension is not a second product runtime. It is a real-Chrome driver
implementation inside the Browser CLI architecture.
