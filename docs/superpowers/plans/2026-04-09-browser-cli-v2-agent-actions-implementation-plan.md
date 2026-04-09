# Browser CLI v2 Agent Actions Implementation Plan

Date: 2026-04-09
Status: Ready for implementation
Related spec: `/Users/hongv/workspace/m-projects/browser-cli/docs/superpowers/specs/2026-04-09-browser-cli-v2-agent-actions-design.md`

## Planning Note

The expected `writing-plans` skill was not available in the current environment. This document is the direct planning fallback and serves the same purpose: an implementation-ready sequence for building `v2`.

## Objective

Build `v2` of Browser CLI as a daemon-backed browser action layer for agents with the following properties:

- one long-lived browser daemon
- one shared browser instance and shared login state
- explicit CLI subcommands with discoverable help
- tab ownership and visibility isolation based on `X_AGENT_ID`
- bridgic-style ref-first interaction
- JSON-first stdout contract for `v2` actions
- clear, fast conflict failures instead of exposed locking semantics

Representative target usage:

```bash
browser-cli open https://example.com
browser-cli tabs
browser-cli snapshot
browser-cli click @8d4b03a9
browser-cli click -h
browser-cli stop
```

## Out of Scope

The following are excluded from this plan:

- workflow DSLs
- recorder or explorer flows
- user-facing session commands
- per-command `--page` targeting
- per-agent isolated cookies or storage state
- multiple browser instances
- hidden fallback from explicit CLI commands to the `read` command path

`v1 read` remains a separate product surface and should not be reshaped into the `v2` daemon model during this plan.

## Delivery Strategy

Build `v2` in seven milestones:

1. daemon and IPC foundation
2. browser service reuse and lifecycle stabilization
3. agent visibility domains and tab registry
4. JSON action contract and CLI command spine
5. core command families for navigation, tabs, HTML, and snapshot
6. ref actions and extended command families
7. integration hardening, smoke validation, and docs

The implementation order matters. A broad command surface is only safe after the daemon, visibility, and tab-conflict model are solid.

## Design Constraints To Preserve

Implementation must preserve these approved design decisions:

- browser uniqueness is a daemon invariant
- browser/profile reuse follows the existing `v1` strategy
- CLI auto-starts the daemon if needed
- daemon stays alive until explicit `stop`
- `X_AGENT_ID` controls visibility, not storage isolation
- commands default to the current domain's active tab
- conflicts fail fast with explicit errors
- `v2` commands are JSON-first
- `v1 read` stays content-first and one-shot

## Repository Impact

Expected new or expanded package areas:

```text
src/browser_cli/
  cli/
  daemon/
  actions/
  agent_scope/
  tabs/
  browser/
  outputs/
  runtime/
tests/
  unit/
  integration/
  smoke/
docs/
```

The existing `browser/`, `profiles/`, and parts of `runtime/` should be reused where practical instead of duplicated.

## Milestone 1: Daemon And IPC Foundation

### Deliverables

- local daemon process bootstrap
- daemon run-info persistence
- local IPC transport
- request/response envelope shared by CLI and daemon
- explicit `stop` support

### Tasks

1. Create daemon package structure.
   Expected modules:
   - `src/browser_cli/daemon/server.py`
   - `src/browser_cli/daemon/client.py`
   - `src/browser_cli/daemon/transport.py`
   - `src/browser_cli/daemon/state.py`

2. Define a daemon request envelope.
   Minimum fields:
   - command/action name
   - normalized arguments
   - resolved `agent_id`
   - request id for tracing

3. Define a daemon response envelope.
   Minimum fields:
   - `ok`
   - `data`
   - `meta`
   - `error_code` when failed
   - short error message when failed

4. Implement daemon auto-start from CLI.
   Rules:
   - first CLI request starts the daemon
   - repeated CLI calls reuse it
   - `stop` does not auto-start a stopped daemon just to stop nothing

5. Persist minimal run-state information to disk so the CLI can discover a live daemon.

6. Add daemon startup and shutdown tests using a temporary run directory.

### Acceptance Criteria

- CLI can auto-start the daemon on first call.
- Repeated CLI calls reuse the same daemon process.
- `browser-cli stop` shuts down the daemon cleanly.
- The transport contract is test-covered and stable before browser actions land.

## Milestone 2: Browser Service Reuse And Lifecycle Stabilization

### Deliverables

- one browser service owned only by the daemon
- reuse of `v1` profile discovery and fallback logic
- stable browser startup and shutdown under daemon mode
- internal browser service API separated from one-shot `read`

### Tasks

1. Extract or wrap browser-launch logic from `v1` so the daemon can own a long-lived browser service without depending on `read_runner`.

2. Reuse the existing profile selection rules:
   - prefer existing local Chrome profile
   - fall back to `~/.browser-cli/default-profile`

3. Make the browser service lazy-started by the daemon.
   The daemon may come up before the browser is opened, but only one browser instance may exist.

4. Ensure browser teardown is clean on:
   - explicit `stop`
   - daemon crash recovery path
   - stale run-info cleanup

5. Add test coverage for:
   - browser service start once
   - browser service reuse across many commands
   - profile fallback still behaving correctly in daemon mode

### Acceptance Criteria

- The daemon never creates more than one browser instance.
- Browser startup is reusable across multiple commands.
- Existing profile fallback still works under daemon ownership.
- `v1 read` still functions after the browser-service extraction.

## Milestone 3: Agent Visibility Domains And Tab Registry

### Deliverables

- `X_AGENT_ID` resolution
- public-domain fallback
- tab ownership metadata
- per-domain `active_tab`
- fast conflict detection for in-flight tab operations

### Tasks

1. Add an agent-scope module that resolves:
   - explicit `X_AGENT_ID`
   - implicit `public` domain when missing

2. Implement a tab registry owned by the daemon.
   Each tab record should track:
   - `page_id`
   - `owner_agent_id`
   - `created_at`
   - `last_used_at`
   - current `url`
   - current `title`
   - transient busy request metadata

3. Implement visibility rules:
   - a domain sees only its own tabs
   - the public domain sees only public tabs

4. Implement domain-local `active_tab` behavior.
   Rules:
   - `open` and `new-tab` set the current domain's `active_tab`
   - `switch-tab` only switches within visible tabs
   - closing the active tab selects another visible tab when possible

5. Implement optimistic conflict handling.
   Rule:
   - if a mutation command targets a busy active tab in the same domain, fail fast with `AGENT_ACTIVE_TAB_BUSY`

6. Add unit tests for ownership, visibility, active-tab replacement, and busy-state transitions.

### Acceptance Criteria

- Two different `X_AGENT_ID` values do not see one another's tabs.
- The public domain remains isolated from named domains.
- Busy-tab conflicts produce stable, test-covered errors.
- No user-facing session concept is needed to get isolation.

## Milestone 4: JSON Action Contract And CLI Command Spine

### Deliverables

- shared action registry
- explicit CLI subcommand registration
- JSON success contract for `v2`
- centralized error mapping and exit codes
- per-command help text

### Tasks

1. Create a canonical action registry.
   It should define:
   - action name
   - argument schema
   - daemon handler binding
   - JSON response shape expectations

2. Implement CLI wrappers as thin argument parsers over the action registry.

3. Preserve explicit help discoverability:
   - `browser-cli -h`
   - `browser-cli click -h`
   - grouped help sections where helpful

4. Standardize success stdout for `v2` commands.
   Minimum shape:

   ```json
   {
     "ok": true,
     "data": {},
     "meta": {}
   }
   ```

5. Centralize failure handling:
   - short stderr summary
   - machine-stable daemon error code
   - stable process exit code mapping

6. Ensure `v1 read` is explicitly excluded from this JSON contract so existing behavior is preserved.

### Acceptance Criteria

- Core CLI help is discoverable without reading source.
- `v2` commands use a uniform JSON success shape.
- Failure mapping is centralized instead of embedded in individual command handlers.
- The command spine is broad enough to grow without duplicating transport logic.

## Milestone 5: Core Command Families

### Deliverables

- first production command set for daemon-backed use
- HTML and snapshot capture on the active tab
- domain-aware tab management
- basic navigation and page-state inspection

### Command Scope

This milestone should land the minimum command families that make the platform usable:

- `open`
- `info`
- `html`
- `snapshot`
- `tabs`
- `new-tab`
- `switch-tab`
- `close-tab`
- `close`
- `stop`
- `reload`
- `back`
- `forward`

### Tasks

1. Implement daemon handlers for the core commands above.

2. Reuse the bridgic-style snapshot/ref implementation already internalized in `v1`.

3. Add JSON payload definitions for:
   - page info
   - HTML content
   - snapshot content
   - tab lists

4. Ensure all handlers resolve the target through the current domain's `active_tab`, not global browser state.

5. Add integration tests covering:
   - open then snapshot
   - open then html
   - new-tab then tabs then switch-tab
   - close-tab active-tab reassignment
   - domain isolation across tabs

### Acceptance Criteria

- Agents can open pages, inspect tabs, switch tabs, and capture HTML/snapshot without touching `read`.
- `tabs` only returns visible tabs for the current domain.
- Snapshot output still contains stable refs needed for later actions.

## Milestone 6: Ref Actions And Extended Command Families

### Deliverables

- ref-driven interaction commands
- keyboard, mouse, script, wait, and verification actions
- selected observation and storage actions
- compatibility-oriented command breadth close to bridgic-browser, without copying its public contract verbatim

### Command Scope

This milestone should add the remaining approved command families in waves:

1. Ref interactions:
   - `click`
   - `double-click`
   - `hover`
   - `focus`
   - `fill`
   - `fill-form`
   - `select`
   - `options`
   - `check`
   - `uncheck`
   - `scroll-to`
   - `drag`
   - `upload`

2. Keyboard, mouse, and evaluation:
   - `type`
   - `press`
   - `key-down`
   - `key-up`
   - `scroll`
   - `mouse-click`
   - `mouse-move`
   - `mouse-drag`
   - `mouse-down`
   - `mouse-up`
   - `eval`
   - `eval-on`
   - `wait`
   - `wait-network`

3. Observation, storage, and verification:
   - `screenshot`
   - `pdf`
   - `network-start`
   - `network`
   - `network-stop`
   - `console-start`
   - `console`
   - `console-stop`
   - `cookies`
   - `cookie-set`
   - `cookies-clear`
   - `storage-save`
   - `storage-load`
   - `verify-text`
   - `verify-visible`
   - `verify-url`
   - `verify-title`
   - `verify-state`
   - `verify-value`
   - `search`

### Tasks

1. Add command handlers in the order listed above, not all at once.

2. Keep ref-based actions authoritative.
   Commands that depend on refs must fail clearly on:
   - `REF_NOT_FOUND`
   - `STALE_SNAPSHOT`

3. Normalize commands that naturally return lists or large blobs into the shared JSON contract.

4. Reuse bridgic-browser internals selectively, but do not regress into text-first output.

5. Add focused integration tests per wave before moving to the next wave.

### Acceptance Criteria

- Ref-first action chains are stable across representative fixture pages.
- Script, keyboard, and mouse actions operate on the current domain's active tab.
- Extended command families preserve the same help, JSON, and error conventions as core commands.

## Milestone 7: Integration Hardening, Smoke Validation, And Docs

### Deliverables

- full test matrix for the daemon-backed action layer
- smoke checklist for multi-agent usage
- updated README and operational docs
- clear migration notes explaining the split between `read` and daemon-backed commands

### Tasks

1. Expand fixture-based integration coverage for:
   - daemon auto-start and stop
   - repeated command reuse against a single browser
   - multi-domain tab isolation
   - busy-tab conflicts
   - stale snapshot recovery behavior

2. Add smoke guidance for real environments:
   - shared login-state expectations
   - use of `X_AGENT_ID`
   - public-domain behavior
   - daemon stop/reset procedures

3. Update README to show the two product surfaces:
   - `read`
   - daemon-backed action commands

4. Document the most important operational rule:
   `X_AGENT_ID` isolates tab visibility, not cookies or storage state.

5. Add troubleshooting docs for:
   - daemon not available
   - active-tab conflicts
   - no active tab
   - stale refs

### Acceptance Criteria

- The docs explain the mental model without exposing internal complexity.
- Smoke instructions are sufficient for real multi-agent use on a shared login state.
- The test suite catches regressions in daemon lifecycle, visibility, and ref stability.

## Recommended Implementation Slices

For execution, use these slices rather than trying to land the whole milestone set in one patch:

1. daemon skeleton plus transport plus `stop`
2. browser service extraction and daemon ownership
3. `X_AGENT_ID` domain model plus tab registry
4. CLI/action registry plus JSON contract
5. core commands: `open`, `tabs`, `switch-tab`, `snapshot`, `html`, `info`
6. core close/reload/history commands
7. ref interaction wave
8. keyboard/mouse/eval/wait wave
9. observation/storage/verify/search wave
10. docs and smoke hardening

Each slice should preserve a runnable, testable state.

## Risks And Mitigations

### Risk 1: Browser service extraction breaks `v1 read`

Mitigation:
- keep `read` tests green after each browser-service change
- avoid coupling daemon concerns into `read_runner`

### Risk 2: Command surface grows faster than contract discipline

Mitigation:
- require every new command to register through the shared action registry
- require per-command help and JSON output tests

### Risk 3: Agent isolation becomes leaky or confusing

Mitigation:
- keep the rule narrow: isolate tabs and active-tab state only
- document that storage is shared
- test public-domain and named-domain behavior separately

### Risk 4: Busy-state handling becomes flaky

Mitigation:
- keep the policy simple: fail fast, no queue
- store only short-lived busy metadata tied to request ids
- test concurrent calls against the same domain and different domains

### Risk 5: Porting too much from bridgic-browser at once slows delivery

Mitigation:
- reuse internals incrementally by command wave
- prioritize platform stability over command completeness
- keep Browser CLI's public contract independent from bridgic-browser's text-first output

## Definition Of Done

`v2` is done when all of the following are true:

- the daemon auto-starts and stays reusable until explicit stop
- one browser instance is shared across repeated CLI calls
- `X_AGENT_ID` isolates tab visibility and active-tab state
- agents can discover the command surface entirely from help output
- the core and extended command families return stable JSON on success
- conflicts fail fast with explicit, actionable error codes
- `v1 read` still works as its own separate surface
