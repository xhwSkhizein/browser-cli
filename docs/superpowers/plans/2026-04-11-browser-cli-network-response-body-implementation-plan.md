# Browser CLI Network Response Body Implementation Plan

Date: 2026-04-11
Status: Ready for implementation
Related spec:

- `/Users/hongv/workspace/m-projects/browser-cli/docs/superpowers/specs/2026-04-11-browser-cli-network-response-body-design.md`

## Planning Note

The expected `writing-plans` skill was not available in the current
environment. This document is the direct planning fallback and serves the same
purpose: an implementation-ready sequence for the approved network response
body upgrade.

## Objective

Upgrade Browser CLI so that `network-*` becomes a response-capable surface for
agents rather than a request-only log.

The final result should satisfy these approved requirements:

- `network-*` remains the only public family name
- old request-only `network` semantics are removed rather than preserved
- `network-wait` becomes the simple one-shot agent path
- `network` returns completed request/response records
- both request and response headers are included
- response bodies are available through a bounded contract:
  - inline text
  - inline base64
  - artifact path
  - omitted
  - unavailable
- Playwright and extension backends expose the same record shape
- extension mode uses CDP rather than page-runtime patching for network capture

## Out of Scope

This plan intentionally does not include:

- preserving the old request-only meaning of `network`
- adding a separate `http-*` family
- raw packet capture or exact transfer-frame preservation
- unbounded in-memory response retention
- general-purpose HAR export in the first slice
- automatic task refactors beyond docs/examples that should adopt the new API

## Delivery Strategy

Implement the work in seven milestones:

1. public contract and action surface
2. shared network record models and daemon wiring
3. Playwright backend end-to-end
4. extension CDP backend end-to-end
5. bounded body retention and artifact spillover
6. tests and fixtures
7. docs, skill, and old-semantics cleanup

The order matters.

- define one contract first
- validate the contract quickly through Playwright
- then implement the more complex extension/CDP path
- only after both backends are aligned should docs and old request-only code be removed

## Design Constraints To Preserve

Implementation must preserve these approved decisions:

- agents should learn one network mental model, not choose between two families
- `network-wait` must work without requiring a prior `network-start`
- Browser CLI may keep a bounded recent per-tab buffer to support `open` then
  `network-wait`
- large retained bodies should reuse the existing artifact path system
- response body capture should default on, but remain bounded by policy
- request and response headers must be exposed when the backend can read them
- extension mode must rely on `chrome.debugger` / CDP for this feature

## Repository Impact

Primary files or areas expected to change:

```text
src/browser_cli/
  actions/cli_specs.py
  daemon/app.py
  daemon/browser_service.py
  drivers/base.py
  drivers/playwright_driver.py
  drivers/_extension/observe_actions.py
  browser/service.py
  extension/protocol.py
browser-cli-extension/src/
  debugger.js
  background/observe_actions.js
  page_runtime.js
tests/
  unit/
  integration/
docs/
  smoke-checklist.md
  superpowers/specs/
  superpowers/plans/
skills/
  browser-cli-delivery/
  browser-cli-explore/
  browser-cli-converge/
```

The exact file split may evolve during implementation, but the old page-runtime
network patch should not survive the final migration.

## Milestone 1: Public Contract And Action Surface

### Deliverables

- one explicit public `network-*` contract
- `network-wait` added to the action catalog
- old request-log semantics intentionally replaced

### Tasks

1. Update `/Users/hongv/workspace/m-projects/browser-cli/src/browser_cli/actions/cli_specs.py`
   to add `network-wait` and revise help text for `network-*`.
2. Define CLI arguments for:
   - `url_contains`
   - `url_regex`
   - `method`
   - `status`
   - `resource_type`
   - `mime_contains`
   - `timeout_seconds`
   - `include_static`
3. Update daemon action handlers in
   `/Users/hongv/workspace/m-projects/browser-cli/src/browser_cli/daemon/app.py`
   to route the new surface.
4. Update extension protocol capability declarations so the extension contract
   knows about `network-wait`.

### Acceptance Criteria

- Browser CLI exposes one coherent `network-*` family
- help text no longer describes `network` as request-only capture
- there is no competing `http-*` design left in code or docs

## Milestone 2: Shared Network Record Models And Daemon Wiring

### Deliverables

- one shared completed-record model
- tab-scoped recent buffer and capture-session state
- BrowserService explicit methods for wait, start, read, and stop

### Tasks

1. Introduce shared Python-side structures for:
   - completed network record
   - body payload metadata
   - filter matching
   - per-tab recent buffer
   - per-tab capture session state
2. Expand `/Users/hongv/workspace/m-projects/browser-cli/src/browser_cli/drivers/base.py`
   with explicit methods for:
   - `wait_for_network_record`
   - `start_network_capture`
   - `get_network_records`
   - `stop_network_capture`
3. Update BrowserService and daemon wiring so `network` means completed records,
   not request logs.
4. Implement recent-buffer-first semantics for `network-wait`.

### Acceptance Criteria

- daemon and driver layers share one record contract
- `open` followed by `network-wait` is supported through the bounded recent buffer
- there is no remaining Python-side assumption that `network` returns request-only data

## Milestone 3: Playwright Backend End-To-End

### Deliverables

- Playwright path returns full completed records
- `network-wait` works end-to-end in the managed-profile backend

### Tasks

1. Replace Playwright request-only accumulation in
   `/Users/hongv/workspace/m-projects/browser-cli/src/browser_cli/browser/service.py`
   with response-capable assembly using:
   - `page.on("request")`
   - `page.on("response")`
   - `page.on("requestfinished")`
   - `page.on("requestfailed")`
2. Read response bodies only after completion and only when policy allows.
3. Populate:
   - request headers
   - response headers
   - mime type
   - timing
   - failure state
   - body payload
4. Make Playwright the first backend used to validate the public contract before
   extension changes land.

### Acceptance Criteria

- Playwright-backed `network-wait` can return text bodies directly
- Playwright-backed `network` returns completed records with headers and body metadata
- old request-only Playwright behavior is removed

## Milestone 4: Extension CDP Backend End-To-End

### Deliverables

- extension-backed `network-*` implemented through CDP
- page-runtime network monkey-patching removed from the final path

### Tasks

1. Extend `/Users/hongv/workspace/m-projects/browser-cli/browser-cli-extension/src/debugger.js`
   with helpers for:
   - `Network.enable`
   - request / response event handling
   - `Network.getResponseBody`
2. Rework
   `/Users/hongv/workspace/m-projects/browser-cli/browser-cli-extension/src/background/observe_actions.js`
   so `network-*` is driven by debugger/CDP state rather than `page_runtime.js`.
3. Maintain per-tab request assembly state keyed by CDP request id.
4. Emit only completed records into the public buffer and waiters.
5. Remove the old page-runtime `fetch` / `XMLHttpRequest` patch from the final
   `network` implementation.

### Acceptance Criteria

- extension-backed `network-wait` can return completed records with headers and body
- extension no longer depends on page-runtime patching for network capture
- extension and Playwright records are structurally aligned

## Milestone 5: Bounded Body Retention And Artifact Spillover

### Deliverables

- one bounded body retention policy across both backends
- large-body spillover into existing artifact storage

### Tasks

1. Implement body classification:
   - `text`
   - `base64`
   - `path`
   - `omitted`
   - `unavailable`
2. Add internal thresholds for:
   - inline text size
   - inline binary size
   - overall buffer budget
3. Reuse existing artifact path conventions for large bodies.
4. Ensure record payloads still report:
   - `body.bytes`
   - `body.truncated`
   - `body.error` when applicable
5. Keep first-pass thresholds internal rather than exposing new user knobs.

### Acceptance Criteria

- large responses do not remain unbounded in memory
- large bodies still produce usable records via artifact paths
- both backends follow the same `body.kind` semantics

## Milestone 6: Tests And Fixtures

### Deliverables

- unit coverage for record assembly and failure states
- integration coverage for public `network-*`
- fixtures that exercise JSON, text, binary, timeout, and failure paths

### Tasks

1. Add unit tests for:
   - filter matching
   - recent-buffer-first `network-wait`
   - body classification
   - failure and unavailable semantics
2. Extend integration fixtures to provide:
   - JSON response
   - HTML/text response
   - binary response
   - failing response
   - multi-request page flow
3. Update integration tests so `network` expectations assert:
   - completed records
   - request headers
   - response headers
   - body contract
4. Add backend parity tests where practical so extension and Playwright are
   checked against the same public behavior.

### Acceptance Criteria

- integration tests prove `network-wait` for at least one body-dependent flow
- unit tests cover error and policy branches, not only success cases
- old request-only expectations are removed

## Milestone 7: Docs, Skill, And Old-Semantics Cleanup

### Deliverables

- docs and skill content teach the new network model
- old request-only code paths and wording removed

### Tasks

1. Update:
   - `/Users/hongv/workspace/m-projects/browser-cli/docs/smoke-checklist.md`
   - task examples
   - Browser CLI docs that mention network observation
2. Update the delivery/explore/converge skill references to prefer:
   - `network-wait` for response-dependent tasks
   - `network-start/network/network-stop` for broader collection
3. Remove obsolete wording that says Browser CLI only captures network requests.
4. Remove dead code from:
   - page-runtime network patching
   - old request-only result shaping
   - stale tests/docs tied to the removed semantics

### Acceptance Criteria

- docs and skill content match the implemented contract
- the repo no longer contains two meanings for `network`
- smoke flows prove the upgraded feature, not the removed one

## Recommended Sequencing Notes

- Land Milestones 1 and 2 first so all downstream work targets one contract.
- Use Milestone 3 to validate the API quickly before extension complexity.
- Do not partially ship extension CDP capture while old page-runtime `network`
  remains the active behavior.
- Cleanup should happen in the same implementation arc, not as a later legacy
  pass.

## Verification Checklist

Before calling the work complete, verify:

- `network-wait` works after `open` without prior `network-start`
- `network` records include both request and response headers
- text responses can be parsed directly from Browser CLI output
- binary responses either inline safely or spill to artifacts
- large bodies do not cause uncontrolled memory growth
- extension and Playwright backends pass the same public expectations
- no old request-only `network` semantics remain in code or docs
