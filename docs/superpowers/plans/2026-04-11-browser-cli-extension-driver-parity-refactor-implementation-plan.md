# Browser CLI Extension Driver Parity Refactor Implementation Plan

Date: 2026-04-11
Status: Ready for implementation
Related spec:

- `/Users/hongv/workspace/m-projects/browser-cli/docs/superpowers/specs/2026-04-11-browser-cli-extension-driver-parity-refactor-design.md`

## Planning Note

The expected `writing-plans` skill was not available in the current
environment. This document is the direct planning fallback and serves the same
purpose: an implementation-ready sequence for the approved extension-driver
parity refactor.

## Objective

Refactor Browser CLI so that:

- the effective driver contract is explicit and complete
- `playwright_driver` and `extension_driver` implement the same full contract
- BrowserService no longer discovers backend support through dynamic attribute
  passthrough
- extension capability reporting becomes granular and honest
- extension-driver parity is improved in priority order, with P0 closing the
  most damaging real-world gaps first

## Out of Scope

This plan intentionally does not include:

- daemon JSON contract changes
- moving semantic refs into the extension
- preserving refs across cross-driver rebinding
- immediate completion of all `trace-*`, `video-*`, and similar long-tail
  extras
- replacing the current extension transport with Native Messaging

## Delivery Strategy

Implement the work in seven milestones:

1. full driver contract definition
2. explicit Playwright driver migration
3. strict BrowserService integration
4. granular extension capability model
5. P0 parity fixes
6. parity test suite
7. P1/P2 extension domain expansion

The key constraint is sequencing: structural refactor first, feature fill-in
second. Do not continue adding isolated extension methods on top of the
current implicit capability model.

## Design Constraints To Preserve

Implementation must preserve these approved decisions:

- daemon remains the only product control plane
- semantic snapshot generation, ref registry, and ref resolution remain
  daemon-owned
- extension remains a raw browser execution backend
- driver rebinding semantics do not change
- daemon action catalog remains the product truth
- `status` and popup remain user-facing sources of truth for extension
  readiness

## Repository Impact

Primary files or areas expected to change:

```text
src/browser_cli/drivers/
  base.py
  playwright_driver.py
  extension_driver.py
src/browser_cli/daemon/
  browser_service.py
src/browser_cli/extension/
  protocol.py
browser-cli-extension/src/
tests/unit/
tests/integration/
docs/
  extension-driver-gaps.md
  superpowers/specs/
  superpowers/plans/
AGENTS.md
README.md
```

## Milestone 1: Full Driver Contract Definition

### Deliverables

- expanded explicit driver contract in `src/browser_cli/drivers/base.py`
- one method per daemon action family
- no hidden reliance on backend passthrough for contract completeness

### Tasks

1. Audit the daemon action catalog in
   `/Users/hongv/workspace/m-projects/browser-cli/src/browser_cli/daemon/app.py`.
2. Expand `BrowserDriver` so it covers the full action surface that daemon can
   dispatch today.
3. Group methods by domain:
   - page lifecycle
   - locator and ref interaction
   - keyboard and mouse
   - wait and verify
   - network and console
   - cookies and storage
   - artifacts and dialogs
   - tracing and video
4. Add or update driver models where useful to keep signatures clear.

### Acceptance Criteria

- daemon public actions are fully representable through the driver contract
- there is no remaining need to infer support from `__getattr__`

## Milestone 2: Explicit Playwright Driver Migration

### Deliverables

- `PlaywrightDriver` explicitly wraps the full contract
- `PlaywrightDriver.__getattr__` removed

### Tasks

1. Enumerate every Playwright-backed operation currently obtained through
   passthrough into `browser/service.py`.
2. Add explicit wrapper methods for the full contract.
3. Remove `__getattr__`.
4. Fix all direct callers that relied on passthrough behavior.

### Acceptance Criteria

- `playwright_driver.py` has no `__getattr__`
- Playwright parity remains intact after the explicit migration

## Milestone 3: Strict BrowserService Integration

### Deliverables

- BrowserService calls only explicit driver methods
- BrowserService dynamic unsupported fallback removed

### Tasks

1. Replace BrowserService calls that rely on dynamic backend attribute lookup
   with explicit driver calls.
2. Remove `BrowserService.__getattr__`.
3. Keep daemon-owned responsibilities unchanged:
   - snapshot registry
   - ref resolution
   - busy-state
   - rebinding
4. Make unsupported functionality visible in tests during implementation rather
   than at runtime after shipping.

### Acceptance Criteria

- BrowserService has no dynamic backend fallback path
- all daemon actions route through explicit BrowserService and driver methods

## Milestone 4: Granular Extension Capability Model

### Deliverables

- finer-grained extension capability namespace
- status and popup can reflect real extension readiness

### Tasks

1. Replace the coarse `CORE_EXTENSION_CAPABILITIES` shape in
   `/Users/hongv/workspace/m-projects/browser-cli/src/browser_cli/extension/protocol.py`
   with domain-granular capability identifiers.
2. Update extension hello payload generation in
   `/Users/hongv/workspace/m-projects/browser-cli/browser-cli-extension/src/background.js`.
3. Update daemon runtime-status reporting to surface these capabilities.
4. Update popup and status rendering if needed so they no longer imply full
   parity when only partial parity exists.

### Acceptance Criteria

- extension readiness is granular, not binary or misleading
- BrowserService can reason about extension support using explicit capability
  data

## Milestone 5: P0 Parity Fixes

### Deliverables

- structural P0 gaps closed
- high-value real-world parity restored

### Tasks

1. Align `eval` semantics so extension and Playwright return equivalent results
   for the same expression forms.
2. Implement extension `screenshot`.
3. Implement extension `wait-network`.
4. Implement extension `cookie-set`.
5. Implement extension `cookies-clear`.
6. Implement extension `verify-visible`.
7. Update docs to correct any outdated assumption that snapshot state ownership
   belongs in the extension.

### Acceptance Criteria

- the Nitter-style eval mismatch is resolved
- screenshot works in extension mode
- P0 actions no longer fail with `DRIVER_UNSUPPORTED`

## Milestone 6: Parity Test Suite

### Deliverables

- driver contract test coverage
- action parity test coverage
- semantic behavior test coverage

### Tasks

1. Add shared driver contract tests that run against both drivers where
   possible.
2. Add daemon action parity tests by domain:
   - lifecycle
   - interaction
   - keyboard and mouse
   - wait and verify
   - network and console
   - cookies and storage
   - artifacts
3. Add semantic behavior tests focused on:
   - eval
   - snapshot and ref flows
   - wait behavior
   - verify behavior
   - cookies and storage payload shape
4. Keep real extension smoke as a documented manual gate outside CI.

### Acceptance Criteria

- parity regressions are caught by tests, not discovered ad hoc during tasks
- tests can identify which driver domain is drifting

## Milestone 7: P1/P2 Domain Expansion

### Deliverables

- common extension parity domains filled in after P0
- `extension_driver` internals reorganized by domain

### Tasks

1. Refactor `extension_driver.py` into themed internal modules or helpers:
   - page actions
   - locator actions
   - keyboard and mouse actions
   - network and console actions
   - cookies and storage actions
   - artifact and dialog actions
2. Decompose extension background dispatch along the same themes.
3. Implement P1 actions:
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
4. Implement P2 actions:
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
   - remaining low-frequency ref wrappers

### Acceptance Criteria

- extension parity reaches the approved public action surface except for the
  explicitly deferred P3 items
- driver and extension source layout are both organized by domain instead of
  growing as single large files

## Validation Sequence

Run this validation sequence after each milestone where applicable:

1. targeted unit and integration tests
2. `./scripts/guard.sh`
3. `./scripts/lint.sh`
4. `./scripts/check.sh` before milestone close

For milestones touching extension runtime behavior, also perform a manual
smoke:

1. reload unpacked extension
2. run `browser-cli status`
3. trigger daemon start
4. verify popup capability display
5. verify backend selection and key action behavior

## Risk Management

- Expanding the driver contract will likely surface many breakages at once.
  This is expected and should be treated as progress, not instability.
- Some extension features may need behavioral approximation rather than strict
  implementation equivalence. Those approximations must be documented and
  tested explicitly.
- Large payload transport limits may block artifact parity unless discovered
  early in the parity test phase.

## Suggested Implementation Slices

Recommended slice order inside the milestones:

1. full contract plus Playwright explicit wrappers
2. BrowserService strictness
3. granular capability model
4. eval semantics fix
5. screenshot plus wait-network
6. cookie mutation plus verify-visible
7. parity test harness
8. extension driver domain split
9. P1 actions
10. P2 actions

## Completion Definition

This plan is complete when:

- the full driver contract is explicit
- Playwright no longer relies on passthrough magic
- BrowserService no longer relies on dynamic unsupported fallback
- extension supports the high-priority public action surface directly
- remaining deferred items are limited to the accepted P3 set
- parity tests and docs make future drift obvious
