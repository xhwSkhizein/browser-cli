# Browser CLI Extension Driver Parity Refactor Design

Date: 2026-04-11
Status: Proposed
Owner: Codex

## Summary

This spec defines the refactor needed to make `extension_driver` converge toward `playwright_driver` as a first-class backend, not a reduced compatibility layer.

The main change is architectural: Browser CLI must stop treating the effective driver capability surface as an implicit mix of:

- daemon action handlers
- `BrowserDriver` base methods
- `PlaywrightDriver.__getattr__` passthrough into the Playwright browser service

Instead, Browser CLI will define one explicit full driver contract aligned to the daemon's public action catalog. Both `playwright_driver` and `extension_driver` must implement that contract directly. BrowserService will stop relying on dynamic attribute fallback to discover whether a backend supports an action.

The goal is not only to "add missing methods". The goal is to make parity measurable, testable, and maintainable.

## Current Findings

The current gap analysis in [extension-driver-gaps.md](../../extension-driver-gaps.md) is directionally correct, but not fully accurate against the current codebase.

### Accurate findings

- `extension_driver` does not yet cover the full daemon action surface.
- A meaningful set of higher-level actions still works only on the Playwright path because `PlaywrightDriver` exposes the underlying browser service through `__getattr__`.
- Runtime parity issues exist even for actions that nominally exist on both drivers.

### Outdated or incomplete findings

- `extension_driver` already implements the current `BrowserDriver` base contract; the larger missing surface lives above that base class.
- `sync_snapshot` and `clear_snapshot` should remain daemon-side responsibilities. They are not extension responsibilities in the target architecture.
- The largest current problems are not only missing methods. They also include:
  - mismatched `eval` semantics
  - extension capability reporting that is too coarse
  - runtime fallback via `BrowserService.__getattr__`
  - missing parity tests for full action groups

## Goals

- Define one explicit driver contract that matches Browser CLI's product action surface.
- Make `playwright_driver` and `extension_driver` implement the same contract directly.
- Remove dynamic capability discovery via `PlaywrightDriver.__getattr__` and `BrowserService.__getattr__`.
- Make extension runtime status report real capability shape instead of a coarse "core complete" signal.
- Close high-value parity gaps first: action support and semantic consistency before lower-value extras.
- Add parity-oriented tests that continuously compare both drivers.

## Non-Goals

- This refactor does not change daemon JSON contract shape.
- This refactor does not move semantic ref ownership into the extension.
- This refactor does not try to make old refs survive cross-driver rebinding.
- This refactor does not require `trace-*`, `video-*`, and the full long tail of optional extras to be completed in the first implementation slice.

## Architecture Decision

### Single explicit full driver contract

The daemon action catalog is the product truth. The driver contract must be derived from that truth, not from the current minimal `BrowserDriver` base class.

The new full contract must cover all actions currently exposed by the daemon:

- page lifecycle
  - `open/new-tab/close/switch/info/html/snapshot/reload/back/forward/resize`
- locator and ref interaction
  - `click/double-click/hover/focus/fill/fill-form/select/options/check/uncheck/scroll-to/drag/upload/eval-on`
- keyboard and mouse
  - `type/press/key-down/key-up/scroll/mouse-click/mouse-move/mouse-drag/mouse-down/mouse-up`
- waiting and verification
  - `wait/wait-network/verify-text/verify-visible/verify-url/verify-title/verify-state/verify-value`
- observability and state
  - `console-start/console/console-stop/network-start/network/network-stop/cookies/cookie-set/cookies-clear/storage-save/storage-load`
- artifacts and runtime extras
  - `screenshot/pdf/dialog-* / trace-* / video-*`

The exact Python method names may remain implementation-oriented, but the contract must fully represent this action surface.

### Daemon retains semantic ownership

The daemon remains the only owner of:

- semantic snapshot generation
- ref registry
- ref resolution
- active tab ownership and busy-state
- driver rebinding

Extension mode continues to provide raw browser execution, not a second semantic system.

## Refactor Scope

### 1. Driver contract expansion

`src/browser_cli/drivers/base.py` will expand from a minimal capability set to a complete explicit contract.

Expected result:

- no daemon action relies on "maybe the backend has this method through passthrough"
- every action has a typed backend method
- unsupported features become explicit implementation gaps, not runtime surprises

### 2. Playwright driver explicitness

`src/browser_cli/drivers/playwright_driver.py` will stop using `__getattr__` as a capability source.

Expected result:

- all supported operations are explicitly wrapped
- parity is visible in code review
- tests can enforce true driver equivalence

### 3. Extension driver modularization

`src/browser_cli/drivers/extension_driver.py` is currently a single file that mixes:

- page id to tab id mapping
- protocol request dispatch
- output shaping

It should be split by theme into internal helpers or mixins:

- page actions
- locator/ref actions
- keyboard and mouse actions
- network and console actions
- cookies and storage actions
- artifact actions
- dialog and tracing actions

Expected result:

- extension parity work can proceed by domain
- tests can map directly onto implementation areas

### 4. BrowserService strictness

`src/browser_cli/daemon/browser_service.py` must stop using `__getattr__` to dynamically surface Playwright-only behavior or extension unsupported fallbacks.

Expected result:

- BrowserService only calls explicit driver methods
- unsupported actions fail at implementation time and test time, not only in production

### 5. Capability model refinement

`src/browser_cli/extension/protocol.py` currently uses a coarse `CORE_EXTENSION_CAPABILITIES` set. This is insufficient once Browser CLI supports partial parity by domain.

Capabilities should become fine-grained, for example:

- `page.open`
- `page.snapshot`
- `locator.click`
- `locator.double_click`
- `artifact.screenshot`
- `cookies.read`
- `cookies.mutate`
- `network.wait_idle`
- `dialog.handle`

Expected result:

- popup and `browser-cli status` can show real extension readiness
- BrowserService rebinding decisions can be more honest
- integration and smoke output can identify partial parity precisely

### 6. Extension action dispatch modularization

`browser-cli-extension/src/background.js` currently handles all extension actions in one switch.

It should be decomposed into themed modules mirroring the driver domains:

- workspace and tab actions
- page and navigation actions
- locator and ref actions
- keyboard and mouse actions
- network and console actions
- storage and cookies actions
- artifacts and dialogs

Expected result:

- protocol growth remains maintainable
- action coverage is easier to audit
- parity tests can point at the responsible module

## Priority Plan

### P0: contract integrity and high-value parity

These must land first.

- expand the full driver contract
- remove `PlaywrightDriver.__getattr__`
- remove BrowserService dynamic unsupported fallback path
- align `eval` semantics between drivers
- implement extension `screenshot`
- implement extension `wait-network`
- implement extension `cookie-set` and `cookies-clear`
- implement extension `verify-visible`
- correct docs and code to keep snapshot registry ownership daemon-side

Rationale:

- these are either structural prerequisites or already causing real user-visible failures during exploration

### P1: common interaction parity

- `double_click`
- `hover`
- `focus`
- `evaluate_on`
- `fill_form`
- `list_options`
- `type_text`
- `press_key`
- `wheel`
- `upload`
- `dialog-*`

Rationale:

- these are frequent enough to matter in real tasks and should not remain Playwright-only

### P2: full interactive parity

- `key_down`
- `key_up`
- `mouse_move`
- `mouse_click`
- `mouse_drag`
- `mouse_down`
- `mouse_up`
- `drag`
- `pdf`
- `search`
- remaining lower-frequency ref wrappers

### P3: deferred advanced artifacts

- `trace-*`
- `video-*`

These remain important but are explicitly lower priority than command parity and semantic consistency.

## Semantic Consistency Requirements

Parity is not only "method exists". The following behaviors must converge:

- `eval`
  - the same expression shape should return equivalent values on both drivers
- `snapshot`
  - daemon-side semantic ref ownership stays unchanged
  - extension remains a raw snapshot input provider
- `wait`
  - timeout and text matching semantics should align
- `verify`
  - visible, state, value, text, title, and URL checks should report equivalent pass/fail semantics
- `cookies` and `storage`
  - payload shape should align across drivers

## Testing Strategy

### Driver contract tests

One shared suite should run against both drivers and verify the complete explicit contract.

### Action parity tests

Daemon action groups must be exercised against both drivers:

- lifecycle
- interaction
- keyboard and mouse
- waiting and verify
- network and console
- cookies and storage
- artifacts

The test oracle is behavioral equivalence, not implementation identity.

### Semantic behavior tests

These focus on actions that are especially prone to drift:

- `eval`
- snapshot and ref flows
- wait behavior
- verify behavior
- cookies and storage payload shape

### Real extension smoke

Manual smoke remains required for:

- unpacked extension load
- daemon handshake
- workspace window creation
- real Chrome execution
- `status` / popup capability visibility

## Acceptance Criteria

This refactor is complete when all of the following are true:

- Browser CLI no longer relies on `PlaywrightDriver.__getattr__`
- BrowserService no longer dynamically exposes Playwright-only methods through `__getattr__`
- the driver contract explicitly covers the full daemon action surface
- extension supports all currently public high-priority actions without runtime `DRIVER_UNSUPPORTED` surprises
- remaining non-parity items are explicitly limited to the accepted deferred set
- `browser-cli status` and extension popup report granular capability state, not a misleading coarse "complete"
- parity tests run continuously and clearly identify per-domain regressions

## Rollout

Recommended implementation order:

1. expand driver contract
2. make PlaywrightDriver explicit
3. make BrowserService strict
4. refine extension capability model
5. implement P0 extension actions and semantic fixes
6. add parity test suites
7. implement P1 and P2 domains
8. leave P3 as follow-up work

## Risks

- expanding the driver contract will initially create a large number of compile-time or test-time failures; this is expected and desirable
- extension parity work may reveal transport-size or protocol-shape limitations that must be fixed alongside action support
- some low-level actions may not map one-to-one onto Chrome extension APIs and will need clearly documented behavioral approximations

## Recommendation

Proceed with a contract-first parity refactor.

Do not continue the current pattern of patching isolated `extension_driver` methods while keeping capability discovery implicit. That pattern makes parity impossible to measure and will keep reintroducing drift between the two backends.
