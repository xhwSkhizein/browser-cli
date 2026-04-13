# Browser CLI Network Response Body Design

Date: 2026-04-11
Status: Implemented on main
Owner: Codex
Repo: `/home/hongv/workspace/browser-cli`

## Summary

This spec upgrades Browser CLI's `network-*` actions from a request-metadata
observer into a response-capable network inspection surface that agents can use
directly.

Update on 2026-04-14:

- the response-capable `network-*` contract is now implemented on `main`
- the Douyin workaround described below should be read as historical motivation
  for the design, not as the current product limitation

The key product decision is:

- keep the public family name as `network-*`
- replace the old request-only semantics instead of introducing a second family
- add `network-wait` as the simple agent-first entrypoint
- make `network` return completed request/response records, including headers
  and optionally body data
- remove the current page-patched extension implementation and replace it with
  driver-level capture

The goal is to make tasks like "wait for a signed JSON response and parse it"
work directly through Browser CLI without extra `performance` probing, cookie
replay, or ad hoc Python HTTP logic inside `task.py`.

## Historical Problem Statement

At the time this spec was written, Browser CLI exposed:

- `network-start`
- `network`
- `network-stop`

but the actual behavior was only request capture:

- extension mode monkey-patches `fetch` and `XMLHttpRequest` in page runtime
- Playwright mode listens for request events only
- response headers and response bodies are not part of the public contract

That was insufficient for real browser automation tasks where the browser is
valuable precisely because it can execute signed requests and receive the
resulting response bodies.

The Douyin download validation exposed the gap clearly:

- Browser CLI could open the page and let the site generate signed detail URLs
- Browser CLI could not directly return the `aweme/detail` JSON response body
- the task had to fall back to:
  - `eval(performance.getEntriesByType('resource'))`
  - read the full browser cookie jar
  - replay the signed request in Python with `requests`

That path worked, but it:

- reduced task clarity
- increased task implementation size
- duplicated transport logic outside Browser CLI
- made response-dependent tasks less reliable than they should be

## Goals

- Make response bodies available through Browser CLI's public network surface.
- Keep the agent-facing API simple and obvious.
- Avoid introducing a competing `http-*` family.
- Add a one-shot "wait for matching response and return it" command.
- Preserve a buffered capture mode for debugging and multi-response collection.
- Include both request and response headers in returned records.
- Support text, JSON, HTML, and binary responses through one body contract.
- Keep extension mode and Playwright mode behavior aligned.
- Replace the current request-only extension implementation instead of carrying
  legacy semantics forward.

## Non-Goals

- This spec does not preserve the old request-only `network` meaning.
- This spec does not implement raw packet capture or exact wire-level transfer
  framing.
- This spec does not attempt to preserve compressed transfer bytes exactly as
  they appeared on the network.
- This spec does not add a second CLI family such as `http-*`.
- This spec does not make response bodies unbounded in memory.

## Options Considered

### 1. Add a separate `http-*` family

Advantages:

- can keep `network-*` unchanged
- can design a clean response-capable surface from scratch

Disadvantages:

- gives agents two overlapping families to choose from
- increases product surface area and documentation burden
- preserves the old technical debt instead of removing it

Rejected.

### 2. Upgrade `network-*` in place and remove the old implementation

Advantages:

- one obvious family for agents
- removes request-only semantics instead of keeping two models
- keeps naming stable while improving capability

Disadvantages:

- this is a contract break for the old request-only meaning
- tests and docs must migrate in the same iteration

Chosen direction.

### 3. Only add a high-level `wait-response` command

Advantages:

- simplest agent surface for one-shot tasks

Disadvantages:

- does not solve buffered debugging and collection
- would likely require later rework to add full capture anyway

Rejected as incomplete.

## Chosen Direction

Browser CLI will keep the public name `network-*`, but redefine it to mean
completed network records rather than request logs.

The public action set becomes:

- `network-wait`
- `network-start`
- `network`
- `network-stop`

The default agent path should be:

1. perform or trigger page work
2. call `network-wait` with a match condition
3. receive one completed response record with headers and body
4. parse it directly in task logic

The buffered path remains available for broader debugging and harvesting:

1. `network-start`
2. perform one or more page actions
3. `network`
4. `network-stop`

## Public Action Surface

### `network-wait`

Purpose:

- wait for the first matching completed response record

Characteristics:

- should not require a prior `network-start`
- should default to returning body data
- should first check a bounded recent per-tab buffer before waiting for future
  matches
- should timeout clearly when no matching record appears

Recommended match inputs:

- `url_contains`
- `url_regex`
- `method`
- `status`
- `resource_type`
- `mime_contains`
- `timeout_seconds`

### `network-start`

Purpose:

- start a tab-scoped capture session

Characteristics:

- initializes per-tab response assembly state
- initializes the completed-record buffer
- enables body capture using the driver's default policy

### `network`

Purpose:

- return completed response records from the active capture session

Characteristics:

- returns finished records, not half-built request state
- supports `clear` behavior like the current surface
- supports lightweight filtering so agents can narrow results after the fact

### `network-stop`

Purpose:

- stop the current capture session and clean up listeners or driver state

Characteristics:

- must release tab-scoped capture resources
- must not leave hidden body buffers attached to the page after stop

## Record Contract

Each completed record should represent one completed request/response outcome.

Minimum top-level fields:

- `request_id`
- `url`
- `method`
- `resource_type`
- `status`
- `ok`
- `request_headers`
- `request_post_data`
- `response_headers`
- `mime_type`
- `started_at`
- `ended_at`
- `duration_ms`
- `failed`
- `failure_reason`
- `body`

### Headers

Both header sets are required:

- `request_headers`
- `response_headers`

They should preserve the values surfaced by the underlying runtime. Matching and
lookups may be case-insensitive, but Browser CLI should not invent header values
that the runtime did not expose.

### Body Contract

`body` should be a structured object:

- `kind`
- `text`
- `base64`
- `path`
- `bytes`
- `truncated`
- `error`

Allowed `kind` values:

- `text`
- `base64`
- `path`
- `omitted`
- `unavailable`

Interpretation:

- `text`
  - small text-like content is inlined directly
- `base64`
  - small binary content is inlined directly
- `path`
  - large content is written through the existing artifact system and the record
    points to it
- `omitted`
  - the body was intentionally not retained by policy
- `unavailable`
  - Browser CLI expected to read a body but the driver/runtime could not supply
    it

This contract lets agents reason about JSON, HTML, and binary payloads without
special-case code.

## Default Body Policy

Body capture should be enabled by default for the upgraded `network-*` family,
but bounded by internal limits.

Recommended internal policy:

- small text responses inline as `body.text`
- small binary responses inline as `body.base64`
- large responses spill to artifacts and use `body.path`
- impossible-to-read bodies become `body.kind = "unavailable"`

This should be the default for:

- `network-wait`
- `network-start`

The first implementation should favor stable defaults over user-exposed knobs.

## Filtering

The first implementation should support one shared, simple filter model across
`network-wait` and `network`.

Recommended filters:

- `url_contains`
- `url_regex`
- `method`
- `status`
- `resource_type`
- `mime_contains`
- `include_static`

The goal is to cover common agent usage without inventing a complex DSL.

## Rolling Recent Buffer

To keep agent usage simple, Browser CLI should maintain a bounded rolling recent
buffer of completed records per active tab.

`network-wait` should:

1. inspect the recent buffer first
2. return immediately if a matching completed record already exists
3. otherwise wait for the next matching completed record

This matters because agents often execute:

1. `open`
2. `network-wait`

without concurrent orchestration. A recent-buffer-first design keeps that flow
valid for responses that completed shortly before `network-wait` was called.

The rolling buffer should stay bounded and low-cost. `network-start` remains the
explicit command for broader, intentional capture sessions.

## Driver Architecture

## Extension Mode

Extension mode should stop relying on page-runtime monkey-patching for network
capture.

Instead, it should use the existing `chrome.debugger` / CDP foundation already
present in the extension runtime.

Required CDP events and commands:

- `Network.enable`
- `Network.requestWillBeSent`
- `Network.responseReceived`
- `Network.loadingFinished`
- `Network.loadingFailed`
- `Network.getResponseBody`

Per tab, the extension should maintain temporary assembly state keyed by CDP
request id:

- request metadata
- response metadata
- completion/failure state
- optional body retrieval result

Only after a request reaches a terminal state should the extension emit a
completed record into the public buffer or satisfy a `network-wait`.

### Why CDP

CDP is the correct layer because it:

- observes actual browser network traffic instead of page-patched fetch/XHR
- can see response metadata and body data
- aligns with Browser CLI's existing debugger-based architecture

## Playwright Mode

Playwright mode should assemble the same completed record contract using native
page events.

Required hooks:

- `page.on("request")`
- `page.on("response")`
- `page.on("requestfinished")`
- `page.on("requestfailed")`

Body reading should happen only after the response is complete and only when the
current policy says the body should be retained.

The final record shape must match extension mode as closely as possible so that
agent logic and task logic do not branch by backend.

## Daemon And Driver Contract Changes

The explicit driver contract must grow to support the upgraded network model.

At minimum, Browser CLI needs explicit methods for:

- starting capture
- reading captured records
- stopping capture
- waiting for one matching completed record

This should be reflected consistently in:

- `drivers/base.py`
- `playwright_driver.py`
- `extension_driver`
- daemon browser service
- daemon app action handlers
- CLI action catalog
- extension protocol capability lists

## Failure Semantics

Browser CLI must distinguish these states clearly:

- no matching response appeared before timeout
- request failed before response completion
- response completed but body retrieval failed
- body was omitted by policy

Suggested record semantics:

- request failure
  - `failed: true`
  - `failure_reason` populated
- body read failure
  - `body.kind = "unavailable"`
  - `body.error` populated
- intentionally skipped body
  - `body.kind = "omitted"`

`network-wait` should report timeout as a command failure rather than returning
an ambiguous empty success payload.

## Artifact Policy

Large retained bodies should reuse Browser CLI's existing artifact path
conventions rather than inventing a second file-output system.

This keeps screenshots, PDFs, videos, and network body artifacts under one
operational model.

Artifact-backed bodies should still return a normal record with:

- `body.kind = "path"`
- `body.path`
- `body.bytes`

## Agent Impact

This design is explicitly agent-driven.

Today, a task that depends on a response body may need to:

- probe browser `performance` entries
- read browser cookies
- replay signed requests in Python
- reconstruct headers manually

With the new design, the expected task path becomes:

1. perform page work
2. `network-wait` for the matching response
3. parse `record["body"]`

That reduces both task complexity and the number of environment assumptions that
task code must re-implement outside Browser CLI.

## Douyin Example

The intended post-change Douyin flow becomes:

1. `browser-cli open <share-url>`
2. `browser-cli network-wait --url-contains /aweme/v1/web/aweme/detail/`
3. parse the returned JSON body
4. extract `aweme_detail.video.play_addr.url_list[0]`
5. download the chosen media URL

This removes the need for:

- `performance.getEntriesByType('resource')` probing
- cookie-jar replay of the detail request
- ad hoc `requests` logic just to recover the JSON that the browser already saw

## Testing

### Automated Coverage

Extension coverage should verify:

- request and response events are assembled into one completed record
- request and response headers are preserved
- body retrieval works for text responses
- body retrieval works for binary responses
- large bodies spill to artifacts
- `network-wait` resolves exactly once for the first matching record
- request failures and body failures produce the correct record semantics

Playwright coverage should verify the same public contract.

### Integration Scenarios

Required scenarios:

- JSON response after click
- HTML or text response
- binary response
- timeout when no matching response appears
- multi-request capture with `network-start` / `network`
- failed request path
- `include_static` behavior

### Real Browser Smoke

The smoke checklist should be updated to prove at least one body-dependent flow:

- start capture or wait for a response
- trigger a fixture request
- verify returned body text
- verify returned headers
- verify metadata still reports the active backend correctly

## Migration

This change should be a hard semantic replacement, not a compatibility layer.

Required migration work:

- remove the current extension page-runtime request patch for `network`
- replace old request-only docs and tests
- update the skill and examples to teach `network-wait` as the default agent
  path
- update the action catalog and protocol capabilities

The repo should not keep both the old and new meanings of `network`.

## Rollout Recommendation

Recommended implementation order:

1. define the new public contract and driver methods
2. implement Playwright path end-to-end for fast validation
3. implement extension CDP path
4. migrate tests and smoke checklist
5. update skill/docs/examples

This order keeps the product contract clear early while still validating the
more complex extension runtime before calling the work complete.

## Open Questions Resolved

The following design questions are resolved by this spec:

- Should Browser CLI add `http-*`?
  - No. Upgrade `network-*` instead.
- Should the old `network` meaning remain?
  - No. Replace it.
- Should headers be included?
  - Yes, both request and response headers.
- Should agents get a one-shot response path?
  - Yes, through `network-wait`.
- Should large bodies remain in memory?
  - No. Spill them to artifacts.
