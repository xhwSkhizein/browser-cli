# Browser CLI Popup Control Surface Runtime Polish Design

Date: 2026-04-12
Status: Drafted for review
Repo: `/home/hongv/workspace/browser-cli`

## Summary

Browser CLI already has a usable lifecycle baseline:

- `browser-cli status` provides a human-readable runtime diagnosis surface
- `browser-cli reload` provides a deterministic reset path
- the extension popup shows basic extension connectivity and workspace state

The next runtime-polish step should not add more top-level CLI lifecycle
commands. Instead, it should make Browser CLI's real runtime behavior easier to
understand and recover from while preserving the approved Agent-first model.

This iteration should strengthen the extension popup as a human-facing
observation and light-recovery surface, while keeping Agent feedback anchored in
command responses and `runtime-status`.

The core architectural rule is:

- Agent truth stays in command response `meta` and daemon `runtime-status`
- popup mirrors the same runtime semantics for human observers
- popup may offer a small set of safe recovery actions, but it must not become a
  second control plane or a second runtime state machine

## Problem Statement

The current popup is intentionally lightweight. It shows:

- extension connection status
- daemon host and port
- missing extension capabilities
- a minimal workspace window summary
- a `Reconnect now` action

That is enough to confirm whether the extension is alive, but it is not enough
to explain Browser CLI's actual runtime behavior when the system is degraded.

Today the most important runtime truth often lives elsewhere:

- command response metadata reveals driver selection and `state_reset`
- daemon `runtime-status` reveals active driver, pending rebind, and workspace
  state
- popup shows only a partial extension-local view

This creates an interpretation gap during real use:

- a human observer may see the popup and still not understand what the Agent is
  likely to do next
- popup and CLI can drift into presenting different levels of truth
- degraded states such as safe-point fallback, capability-incomplete extension
  sessions, or weak workspace binding are not represented as first-class runtime
  explanations

The goal of this work is not to make the popup the primary product surface. The
goal is to make Browser CLI's runtime legible enough that:

- the Agent keeps receiving machine-readable runtime truth through existing
  channels
- a human observer can quickly understand what is wrong, whether the Agent can
  keep going, and what limited safe recovery actions are available

## Goals

- Preserve Agent-first runtime feedback through command response `meta` and
  daemon `runtime-status`.
- Add a stable daemon-owned runtime presentation model that both CLI and popup
  can consume.
- Upgrade the extension popup from connection-only status to runtime-oriented
  diagnosis and light recovery.
- Make degraded and recovering runtime states explicit and explainable.
- Provide a small set of safe recovery actions in the popup:
  - refresh runtime state
  - reconnect extension transport
  - rebuild Browser CLI workspace binding
- Keep popup actions limited to Browser CLI-owned runtime state.
- Ensure popup language is centered on what Browser CLI and the Agent are doing,
  not on manual operator workflows.

## Non-Goals

- No new top-level lifecycle CLI command family.
- No popup-driven replacement for `browser-cli reload`.
- No popup-driven page actions or general browser control panel.
- No second runtime state model defined only in the extension popup.
- No human-first product pivot; the Agent remains the primary product user.
- No cross-agent tab management or session concepts exposed through popup.
- No forced driver switching control in the popup.

## Options Considered

### 1. Popup-only display improvement

Improve popup presentation while continuing to derive status mostly from
extension-local state.

Advantages:

- smallest implementation
- low risk to daemon contracts

Disadvantages:

- popup remains only a partial view of runtime truth
- state interpretation logic drifts into the extension frontend
- CLI and popup can still disagree in degraded situations

Rejected.

### 2. Daemon-owned runtime presentation model plus popup rendering

Add a daemon-owned runtime presentation layer derived from existing runtime
facts. Use it from `runtime-status`, reuse it in `browser-cli status`, and have
popup render the same state for observers.

Advantages:

- keeps one runtime truth source
- aligns Agent-facing and human-facing diagnosis
- gives subsequent runtime and stability work a reusable status contract

Disadvantages:

- touches daemon, CLI, extension bridge, and popup rendering

Chosen direction.

### 3. Popup aggregates multiple sources directly

Let popup query extension-local state and daemon state separately, then infer
runtime meaning in popup code.

Advantages:

- superficially flexible

Disadvantages:

- duplicates runtime interpretation logic
- weakens architectural boundaries
- harder to test and keep aligned over time

Rejected.

## Chosen Direction

This iteration should define a daemon-owned runtime presentation model that
summarizes Browser CLI runtime behavior into a small number of stable,
explainable semantics.

That model should become the shared basis for:

- Agent global diagnosis through `runtime-status`
- human-readable CLI rendering through `browser-cli status`
- popup rendering for human observers

The popup should remain a secondary control surface with a narrow purpose:

- show what Browser CLI is doing now
- show why Browser CLI is degraded or recovering
- show what the Agent is most likely to do next
- expose only a small set of safe, local recovery actions

This keeps the product model consistent:

- command `meta` answers what just happened on this command
- `runtime-status` answers what the runtime currently is
- popup answers what a nearby human should understand about the runtime

## User Model

Browser CLI is Agent-first.

That means:

- the Agent is the primary user
- the popup is not designed to be the Agent's main feedback surface
- the human looking at the popup is usually an observer, not the main operator

The popup therefore should not optimize for broad manual control. It should
optimize for quick comprehension:

- is Browser CLI healthy enough that the Agent can continue
- if not, what is failing
- is Browser CLI already recovering automatically
- if a human needs to help, what limited safe action is appropriate

## Runtime Presentation Model

The new presentation model should be derived from existing daemon/runtime facts
rather than invented separately in the popup.

It should include at least these fields.

### `overall_state`

A top-level state for observer comprehension:

- `healthy`
- `degraded`
- `recovering`
- `broken`

This is for runtime legibility, not a replacement for lower-level driver
details.

### `summary_reason`

A one-line explanation of the most important current condition, for example:

- extension disconnected; Browser CLI will continue on Playwright at the next
  safe point
- extension connected but required capabilities are incomplete
- workspace binding lost; Browser CLI can rebuild its owned workspace state

### `execution_path`

A compact runtime summary of how commands are or will be executed:

- active driver
- whether a rebind is pending
- whether Browser CLI is waiting for a safe-point transition
- whether the most recent command caused a `state_reset`

The point is to answer: what path is the Agent currently on?

### `workspace_state`

A Browser CLI-owned workspace summary:

- whether a workspace window exists
- whether the workspace binding is trusted
- workspace tab count
- active tab summary when known
- busy-tab summary when relevant

This answers whether Browser CLI still has stable control over its own working
surface.

### `recovery_guidance`

A short list of current next-step explanations, written around Browser CLI and
Agent behavior rather than generic operator help.

Examples:

- Agent can continue; the next command will run on Playwright until extension
  connectivity returns
- if extension mode should be active, reopen the popup and retry extension
  reconnect
- if Browser CLI no longer appears to control its workspace, rebuild workspace
  binding

### `available_actions`

A machine-readable set of safe popup actions currently allowed, such as:

- `refresh-status`
- `reconnect-extension`
- `rebuild-workspace-binding`

The popup should render actions from this capability list instead of hardcoding
its own policy assumptions.

## Architecture

### Daemon Runtime Facts

Existing runtime owners remain unchanged:

- `browser_cli.daemon.browser_service` owns driver state, extension health,
  pending rebind, and workspace-related facts
- `browser_cli.tabs` continues to own tab visibility, active-tab tracking, and
  busy-state facts
- the extension runtime continues to own extension transport and workspace
  window mechanics on the Chrome side

These layers should continue to expose raw runtime facts, not popup-specific
rendering decisions.

### Runtime Presentation Assembly

A daemon-side presentation assembly layer should transform raw runtime facts
into the shared runtime presentation model.

Responsibilities:

- classify `healthy`, `degraded`, `recovering`, and `broken`
- produce one stable summary reason
- summarize execution path and workspace control state
- list allowed popup actions
- generate current recovery guidance

This layer should remain daemon-owned so Browser CLI keeps one state
interpretation path.

### CLI Rendering

`browser-cli status` should continue to render human-readable text, but it
should consume the shared runtime presentation model wherever possible instead
of maintaining a separate state-classification path.

The text view may still include more detail than popup, but the meaning of the
top-level state and guidance should stay aligned.

### Popup Rendering

The extension popup should consume the shared runtime presentation model through
the existing extension bridge, then render:

- top-level runtime state
- summary reason
- execution path
- workspace state
- recovery guidance
- allowed actions

The popup should stop acting like an extension-only status sheet. It should
become a Browser CLI runtime observer.

### Extension Bridge

The popup should not query multiple Browser CLI truth sources and merge them in
frontend code.

Instead:

- popup talks to extension background code
- extension background retrieves or caches the daemon-owned runtime presentation
  snapshot
- popup renders that snapshot plus minimal local transport context such as daemon
  host and port

This keeps runtime interpretation out of popup UI code and preserves one
authoritative status path.

## Popup Information Hierarchy

The popup should be structured around four cards or sections.

### 1. Runtime Summary

Always visible at the top:

- overall state badge
- one-line summary reason
- daemon target address

This answers whether the runtime currently looks normal enough to keep waiting.

### 2. Execution Path

Shows how Browser CLI is currently operating:

- active driver
- pending rebind target and reason
- whether Browser CLI is in a safe-point wait
- whether the last observed transition involved a state reset

This explains what route Agent commands are taking.

### 3. Workspace Ownership

Shows whether Browser CLI still controls its own runtime surface:

- workspace window presence
- workspace trust/binding state
- workspace tab count
- active tab summary when available
- busy tab note when relevant

This explains whether Browser CLI still has coherent ownership of its own tabs.

### 4. Recovery

Shows:

- recovery guidance lines
- allowed actions as buttons

The language here should avoid generic help text and instead explain what
Browser CLI or the Agent will likely do next.

## Popup Action Scope

Popup actions must remain narrow, safe, and local to Browser CLI-owned state.

### `Refresh Status`

Purpose:

- fetch a fresh runtime presentation snapshot

Rules:

- no runtime mutation
- always available

### `Reconnect Extension`

Purpose:

- retry extension transport connectivity or handshake

Rules:

- does not force an immediate driver switch
- may update runtime state to `healthy`, `degraded`, or `recovering`
- must return a fresh runtime presentation snapshot

### `Rebuild Workspace Binding`

Purpose:

- restore Browser CLI's control over its owned workspace window and managed tabs

Rules:

- may recreate or rebind Browser CLI-owned workspace state
- must not mutate arbitrary non-Browser-CLI Chrome tabs
- must return a fresh runtime presentation snapshot

### Explicit Exclusions

These must not be added to popup in this iteration:

- full `reload`
- complex stop/start lifecycle orchestration
- page-level actions
- cross-agent tab control
- manual forced driver-switch actions

## Agent Feedback Contract

The popup work depends on strengthening the runtime feedback contract the Agent
already uses.

### Command Response `meta`

Each daemon-backed command should continue to report per-command runtime facts,
including at least:

- `driver`
- `state_reset`

Where useful for runtime recovery, command metadata may also include a compact
runtime note that explains significant transitions without duplicating full
runtime state.

### `runtime-status`

`runtime-status` should expose the shared presentation model alongside the lower
level runtime facts it already returns.

The Agent remains responsible for using command metadata and runtime status to
decide whether to:

- continue immediately
- wait for a safe-point transition
- retry after reconnect
- escalate to `browser-cli reload`

Popup is only a projection of the same truth.

## State Classification Rules

The presentation layer should classify runtime states conservatively.

### `healthy`

Use when:

- Browser CLI runtime is coherent
- active execution path is stable
- no recovery operation is pending

### `degraded`

Use when:

- Browser CLI can still function
- but a preferred path or capability is unavailable

Examples:

- extension disconnected but Playwright fallback is available
- extension connected but missing required capabilities

### `recovering`

Use when:

- Browser CLI is actively in a transition or guided recovery path
- the system is not yet stable, but the path forward is already known

Examples:

- safe-point rebind is pending
- a reconnect or workspace rebuild action is in progress

### `broken`

Use when:

- Browser CLI cannot currently provide a coherent runtime path
- local safe recovery actions are insufficient or unavailable

Examples:

- daemon unreachable with stale state
- workspace control is lost and cannot be rebuilt through safe local recovery

## Error Handling

This iteration should prefer explicit degraded-state explanation over generic
errors whenever the runtime is still recoverable.

The shared presentation model should always try to provide:

- one top-level state
- one summary reason
- one or more recovery guidance lines
- one list of available safe actions

Even when the runtime is broken, popup and CLI should make it clear whether:

- the Agent can continue
- Browser CLI is already attempting recovery
- a human can help with a safe local action
- `reload` is the remaining fallback

## Testing Strategy

The testing focus should be runtime contract alignment, not cosmetic popup
details.

### Unit Tests

- runtime fact to presentation-model mapping
- state classification for `healthy`, `degraded`, `recovering`, and `broken`
- allowed-action selection for different runtime conditions
- recovery guidance generation for representative failure modes

### CLI Tests

- `browser-cli status` reflects the shared presentation state correctly
- status guidance stays aligned with daemon runtime semantics

### Extension Tests

- popup rendering reflects the presentation model rather than extension-local
  assumptions
- reconnect action updates the displayed runtime state correctly
- workspace rebuild action updates the displayed runtime state correctly

### Integration And Smoke Coverage

- extension disconnect followed by safe-point Playwright downgrade
- extension reconnect without manual full reload
- capability-incomplete extension session
- lost workspace binding and safe rebuild
- popup and CLI status agreeing on the same top-level runtime interpretation

## Rollout Notes

This work is intentionally narrower than a full lifecycle redesign.

It should land before long-run stability work because it improves the operator
visibility needed to interpret soak and reconnect failures.

It should land before structural cleanup because it clarifies which runtime
concepts are durable enough to deserve explicit shared contracts.

## Acceptance Criteria

- popup surfaces Browser CLI runtime state rather than only extension-local
  connectivity
- popup and `browser-cli status` agree on top-level runtime interpretation
- Agent-facing truth remains command response `meta` plus `runtime-status`
- popup exposes only safe local recovery actions
- degraded and recovering states explain what Browser CLI and the Agent are
  likely to do next
- no popup action can mutate arbitrary user tabs outside Browser CLI-owned
  workspace state
