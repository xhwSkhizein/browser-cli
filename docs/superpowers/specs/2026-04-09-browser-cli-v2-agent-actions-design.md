# Browser CLI V2 Agent Actions Design

Date: 2026-04-09
Status: Approved for planning
Repo: `/Users/hongv/workspace/m-projects/browser-cli`

## Summary

`v2` is not a workflow system.

The next stage of Browser CLI is a daemon-backed browser action layer for agents: one long-lived browser instance, shared login state, explicit CLI subcommands, stable element refs, tab management, and agent-scoped visibility based on `X_AGENT_ID`.

This design deliberately removes the previously discussed user-facing `session` concept. The product should stay simple for agents:

```bash
browser-cli open https://example.com
browser-cli snapshot
browser-cli click @8d4b03a9
browser-cli tabs
browser-cli switch-tab page_1234
browser-cli click -h
```

Internally, the daemon still tracks ownership, active tabs, and conflict state so concurrent agents do not trample one another.

## Scope Correction

During `v2` brainstorming, the workflow concept was intentionally deferred again.

The correct dependency order is:

1. `v1`: universal page reading
2. `v2`: stable browser primitives for agents
3. `v3`: exploration flows built on those primitives
4. later: reusable workflows built on top of exploration and primitives

This means `v2` is the browser control substrate that future `explore` and `workflow` features will reuse. It is not yet a workflow DSL, recorder, or synthesizer.

## Goals

- Keep exactly one long-lived browser instance per daemon.
- Reuse the existing profile strategy from `v1`, including fallback to `~/.browser-cli/default-profile`.
- Make the browser daemon auto-start when the CLI is called and no daemon is running.
- Keep the daemon alive until an explicit global stop.
- Preserve shared cookie/localStorage/login state across all agent calls.
- Expose a broad, explicit CLI command surface that agents can discover through `browser-cli -h` and per-command help such as `browser-cli click -h`.
- Use bridgic-style stable refs and snapshot-driven interaction as the primary element model.
- Support multiple tabs.
- Isolate concurrent agents by visibility and ownership using `X_AGENT_ID`, not a user-facing `session` abstraction.
- Keep the user model optimistic and simple: default to allowing actions, and return clear conflict errors only when necessary.
- Make `v2` commands JSON-first so agents have one stable machine-readable contract.

## Non-Goals

- No user-facing `session create/run/close` command family.
- No `--page <page_id>` parameter on every command.
- No workflow DSL in `v2`.
- No recorder, explorer, or synthesize pipeline in `v2`.
- No queue management, lease API, claim/release protocol, or other explicit concurrency controls exposed to agents.
- No isolated cookie or storage state per agent.
- No second browser instance per agent.

## Chosen Direction

Three options were considered:

1. Global shared browser with no agent isolation.
2. One shared browser plus internal `X_AGENT_ID` visibility domains.
3. Shared browser plus explicit claim/release locking commands.

Option 2 is the chosen direction.

It keeps the CLI simple while still making concurrent usage defensible. Agents do not need to learn sessions, page flags, or lock management. They only need to set `X_AGENT_ID` when isolation matters. The daemon owns the complexity.

## Product Shape

The external product shape is:

- one daemon-managed browser
- one shared Playwright context and profile
- many tabs
- one active tab per agent visibility domain
- explicit CLI subcommands
- JSON-first stdout for `v2` action commands

The human and agent mental model should be:

- there is one browser
- my agent only sees its own tabs unless it is in the public domain
- my commands act on my current tab
- if the current tab is already being manipulated, I get a clear error and can retry or open a new tab

## Core Architecture

### 1. Daemon

`browser_cli.daemon`

Responsibilities:

- own the long-lived browser lifecycle
- auto-start on first CLI request
- hold the unique browser instance and Playwright context
- reuse the `v1` profile selection and fallback rules
- expose a local IPC interface for CLI requests
- enforce structured command execution and response formatting

The daemon is the only process allowed to talk directly to Playwright objects.

### 2. Agent Namespace Registry

`browser_cli.agent_scope`

Responsibilities:

- resolve the current visibility domain from `X_AGENT_ID`
- treat missing `X_AGENT_ID` as the public shared domain
- maintain agent-scoped active tab pointers
- answer visibility questions such as “which tabs belong to this agent domain?”

This layer does not isolate cookies, localStorage, or browser storage. It only isolates visibility and default targeting.

### 3. Tab Manager

`browser_cli.tabs`

Responsibilities:

- create, close, switch, and enumerate tabs
- attach ownership metadata to each tab
- track each agent domain's `active_tab`
- track transient busy state for mutation commands
- cleanly recover active-tab state when tabs are closed

Each tab record should at minimum carry:

- `page_id`
- `owner_agent_id`
- `created_at`
- `last_used_at`
- current `url`
- current `title`
- busy metadata for the current in-flight request, if any

### 4. Browser Action Registry

`browser_cli.actions`

Responsibilities:

- define the canonical set of daemon actions
- map CLI subcommands to internal browser operations
- normalize success payloads and error codes
- preserve a stable public action contract even if internals change

The action registry is the true internal API. CLI subcommands are thin wrappers over it.

## Concurrency Model

### Browser and State Sharing

- The browser instance is unique.
- The browser context is shared.
- Cookies, localStorage, and login state are shared.
- Agent isolation only applies to tab visibility and default active-tab resolution.

### Visibility Model

- `X_AGENT_ID=<value>` means the call executes within that agent domain.
- Missing `X_AGENT_ID` means the call executes in the shared public domain.
- Tabs created by a domain belong to that domain by default.
- Commands such as `tabs`, `info`, `snapshot`, `html`, and element actions only see the current domain's visible tabs.

### Active Tab Model

- Every agent domain has exactly one `active_tab`, or none.
- Commands without an explicit page argument target the domain's `active_tab`.
- `open` and `new-tab` create a new tab owned by the current domain and make it the domain's `active_tab`.
- `switch-tab` only accepts tabs visible to the current domain and updates that domain's `active_tab`.

### Conflict Model

The system uses an optimistic model:

- commands attempt to run immediately
- no user-facing lock API exists
- no daemon-side action queue is exposed to agents
- conflicts fail fast with explicit errors

If a tab is already being manipulated by another in-flight request in the same domain, the next request fails with a conflict error instead of waiting indefinitely.

The recommended agent recovery path is:

1. retry later if the operation was transient
2. open a new tab if independent work must continue
3. switch strategy if the tab state is no longer what the agent expected

## Element Model

`v2` interaction is ref-first.

The system should reuse the `bridgic-browser` snapshot/ref design as closely as practical:

- `snapshot` returns a bridgic-style accessibility tree
- interactive elements carry stable refs
- ref-based actions are the primary interaction path
- selector-based escape hatches are not part of the primary `v2` contract

This keeps the future `explore` layer aligned with the same abstraction instead of inventing a second targeting model.

## CLI Surface

The CLI remains explicit and help-driven. Agents are expected to discover capabilities from help output and per-command docs.

Representative command groups:

### Navigation and Page State

- `open`
- `search`
- `info`
- `reload`
- `back`
- `forward`
- `html`
- `snapshot`

### Element Interaction

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

### Keyboard, Mouse, and Script

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

### Tab Management

- `tabs`
- `new-tab`
- `switch-tab`
- `close-tab`

### Wait and Observation

- `wait`
- `wait-network`
- `screenshot`
- `pdf`
- `network-start`
- `network`
- `network-stop`
- `console-start`
- `console`
- `console-stop`

### State and Storage

- `cookies`
- `cookie-set`
- `cookies-clear`
- `storage-save`
- `storage-load`

### Verification and Lifecycle

- `verify-text`
- `verify-visible`
- `verify-url`
- `verify-title`
- `verify-state`
- `verify-value`
- `close`
- `stop`

## Command Semantics

### `close`

`close` is domain-local behavior. It closes the current domain's active tab. It does not stop the daemon and does not affect tabs owned by other agent domains.

### `stop`

`stop` is global behavior. It stops the daemon and tears down the unique browser instance. This is primarily an operational command, not an everyday agent command.

### `tabs`

`tabs` returns only the tabs visible to the current domain. Public-domain callers only see public tabs.

### `html` and `snapshot`

Both commands operate on the current domain's active tab and return structured JSON payloads containing the captured content.

## Output Contract

`v2` action commands are JSON-first.

Successful stdout output should use a stable structure:

```json
{
  "ok": true,
  "data": {},
  "meta": {}
}
```

Representative examples:

- `html`: `data.html`
- `snapshot`: `data.tree`, optional `data.refs_summary`
- `tabs`: `data.tabs`
- `info`: `data.page`
- `network`: `data.requests`
- `console`: `data.messages`

This contract is intentionally different from `bridgic-browser`'s text-first CLI surface. The internal daemon may still resemble bridgic's request/response model, but Browser CLI's public `v2` action layer should not mix free-form text and JSON payloads.

## Relationship To v1

`v1 read` should remain unchanged in spirit:

- content-first output
- one-shot browser usage
- HTML by default, snapshot on request

`v2` is a second surface, not a replacement for `read`.

The practical product split becomes:

- `read`: opinionated one-shot content acquisition
- `v2` commands: daemon-backed browser control primitives for agents

This avoids breaking the clean `read` experience while still giving agents a richer control plane.

## Error Handling

The system should use a small, stable set of high-signal error codes.

Initial required errors:

- `DAEMON_NOT_AVAILABLE`
- `NO_ACTIVE_TAB`
- `NO_VISIBLE_TABS`
- `AGENT_ACTIVE_TAB_BUSY`
- `TAB_NOT_FOUND`
- `REF_NOT_FOUND`
- `STALE_SNAPSHOT`
- `INVALID_INPUT`
- `OPERATION_FAILED`

Rules:

- stdout contains only success JSON
- stderr contains a short human-readable error summary
- daemon responses always include a machine-stable error code
- conflict errors do not auto-retry
- commands should fail clearly instead of silently switching tabs or domains

Error messages should be actionable for agents. For example, a busy-tab error should tell the agent to retry later or create a new tab.

## Testing Strategy

### 1. Unit Tests

Cover:

- `X_AGENT_ID` resolution
- public-domain fallback
- tab ownership bookkeeping
- active-tab selection
- conflict detection
- command parameter normalization

### 2. Daemon Integration Tests

Cover:

- daemon auto-start
- repeated CLI calls against the same daemon
- explicit stop and reconnect
- domain visibility rules
- domain-local active-tab switching

### 3. Browser Integration Tests

Cover:

- `open -> snapshot -> click/fill/type/eval`
- `new-tab -> tabs -> switch-tab -> close-tab`
- ref-driven interactions after DOM changes
- stale snapshot failures
- JSON output contract for representative commands

### 4. Smoke Tests

Cover a small set of real-world checks:

- profile reuse
- fallback profile still works under daemon mode
- shared login state across multiple domains
- concurrent calls from different `X_AGENT_ID` values do not see one another's tabs

Real-site smoke tests should remain limited. The primary CI target should stay on fixture-backed integration tests.

## Migration and Reuse

`v2` should reuse as much of the internalized `bridgic-browser` browser core as practical:

- daemon transport ideas
- browser lifecycle management
- snapshot and ref generation
- tab operations
- stealth and persistent context behavior

But the public API should match Browser CLI's goals:

- no user-facing session abstraction
- explicit helpable subcommands
- JSON-first agent contract
- `X_AGENT_ID`-based visibility isolation

## Success Criteria

`v2` is successful when:

- an agent can discover the command surface from `browser-cli -h`
- an agent can inspect per-command help like `browser-cli click -h`
- repeated calls reuse the same daemon and browser instance
- different agents can share login state without seeing one another's tabs
- conflicts fail fast with clear recovery guidance
- ref-first interaction is stable enough to support a later exploration layer
