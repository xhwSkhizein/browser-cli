# Browser CLI Extension Video via CDP Screencast

## Summary

Current extension video recording uses `chrome.tabCapture` plus an offscreen `MediaRecorder`.
This works in local unit tests but fails in real Chrome when triggered through `browser-cli`,
because `chrome.tabCapture.getMediaStreamId(...)` is still gated by Chrome's invocation and
permission model. The result is that extension video is the last remaining real-Chrome parity
gap after trace has already been validated.

This change replaces the extension video backend with a CDP-based screencast pipeline:

- `chrome.debugger` / CDP provides frame delivery through `Page.startScreencast`
- the extension service worker manages screencast session state and frame acknowledgements
- the offscreen document encodes the received frame sequence into a deferred `.webm`
- the public CLI and daemon contracts stay unchanged

The goal is not system-level screen recording fidelity. The goal is a stable, CLI-triggerable,
real-Chrome-compatible video artifact that preserves the current deferred save semantics.

## Goals

- Make `video-start` / `video-stop` work in real Chrome extension mode without `tabCapture`
- Keep the existing daemon JSON contract and CLI surface unchanged
- Keep deferred video materialization semantics unchanged:
  - `video-stop` ends recording and stores a pending artifact
  - artifact bytes are written during `close-tab`, `workspace-close`, or daemon `stop`
- Preserve `.webm` as the output format
- Keep `video-*` in extension required capabilities

## Non-Goals

- Audio capture
- Bit-for-bit equivalence with Playwright video output
- High-frame-rate or cinematic-quality output
- Reworking trace, artifact chunk transport, or semantic ref ownership

## Recommended Approach

There are three viable implementation directions:

1. Continue fixing `tabCapture`
   - Lowest code churn
   - Does not solve the actual real-Chrome blocker reliably

2. Use CDP `Page.startScreencast` and encode frames into `.webm`
   - Avoids `tabCapture` permission gating
   - Preserves current driver and daemon architecture
   - Requires a new frame-buffering and offscreen encoding path

3. Downgrade video to a screenshot-sequence artifact
   - Easier to implement
   - Breaks current public expectations for `video-*`

Recommended option: **2**

It is the only option that keeps the current product contract intact while removing the
permission model that blocks CLI-triggered recording in real Chrome.

## Architecture

### High-Level Flow

1. `video-start`
   - daemon calls `extension_driver.video-start`
   - extension starts a screencast on the managed tab using CDP
   - each incoming frame is acknowledged immediately
   - each incoming frame is forwarded to the offscreen document
   - extension session state transitions to `recording`

2. `video-stop`
   - extension stops CDP screencast delivery
   - offscreen document finalizes the collected frames into a `.webm`
   - encoded bytes are returned to the extension and stored as a pending artifact
   - response preserves current contract:
     - `recording: false`
     - `path`
     - `deferred: true`

3. `close-tab` / `workspace-close` / daemon `stop`
   - extension checks for pending video artifacts
   - if present, it emits the `.webm` through the existing chunked artifact transport
   - then completes the close/shutdown operation

### Ownership

- daemon remains the owner of product semantics, tab lifecycle, and artifact materialization
- extension remains the owner of browser-side screencast capture
- offscreen document remains the owner of heavy media processing

Semantic ref ownership does not change.

## Detailed Design

### Extension Debugger Layer

`browser-cli-extension/src/debugger.js` will gain explicit screencast helpers:

- `startScreencast(tabId, options)`
- `stopScreencast(tabId)`
- `registerScreencastListeners(...)`

Responsibilities:

- call `Page.startScreencast`
- listen for `Page.screencastFrame`
- acknowledge every frame via `Page.screencastFrameAck`
- forward frame payloads and metadata to the registered consumer
- clean up any active screencast waiter/listener on detach or tab close

Default screencast settings:

- format: `jpeg`
- everyNthFrame: `1`
- maxWidth / maxHeight: optional advisory values derived from requested width/height

### Extension Video Session State

`browser-cli-extension/src/background/video_actions.js` will move from stream-recorder state
to screencast session state.

Each tab-scoped video session stores:

- `pageId`
- `requestedPath`
- `recording`
- `pendingBase64`
- `mimeType`
- `width`
- `height`
- `fps`
- `frameCount`
- `startedAt`

Session states:

- `idle`
- `recording`
- `stopped_pending_artifact`
- `flushed`

Rules:

- only one active recording per managed tab
- `video-start` on an already-recording tab fails
- `video-stop` on a non-recording tab fails
- pending artifacts must be flushed before the tab/workspace is closed

### Offscreen Encoding

The offscreen document will stop using `getUserMedia` / `MediaRecorder` over a captured tab stream.
Instead it will implement a frame-driven encoder pipeline.

Recommended implementation:

- create an in-memory canvas matching the first frame size
- decode each incoming JPEG frame into an `ImageBitmap`
- draw it to canvas
- use `canvas.captureStream(fps)` to generate a media stream
- record that stream with `MediaRecorder` into `.webm`
- advance frames on a controlled schedule based on the target fps
- on stop, finalize the recorder and return:
  - `data_base64`
  - `size_bytes`
  - `mime_type`

This is not a perfect real-time recording of the page. It is a stable encoded replay of
captured screencast frames, which is sufficient for Browser CLI's video artifact contract.

### Frame Timing

Default target fps: `8`

Rationale:

- keeps encoding cost and memory pressure reasonable
- aligns with the fact that CDP screencast is a sampling transport, not a full compositor capture
- is adequate for debugging and replay artifacts

`width` / `height` remain advisory:

- they are preserved in metadata
- they may be used to cap screencast dimensions where CDP allows
- they do not guarantee an exact output size

### Artifact Delivery

Artifact delivery does not change semantically.

The existing chunked artifact transport remains the only path for final video bytes.

`video-stop`:

- must not emit artifacts yet
- only stores pending encoded bytes in extension session state

`close-tab`, `workspace-close`, daemon `stop`:

- emit `.webm` through chunked artifact transport
- include `video_path` or `video_paths` in the response

Output format remains `.webm`.

## File-Level Changes

### Extension JavaScript

- `browser-cli-extension/src/debugger.js`
  - add screencast start/stop/listener plumbing

- `browser-cli-extension/src/background/video_actions.js`
  - replace `tabCapture` flow with screencast session orchestration

- `browser-cli-extension/src/offscreen.js`
  - replace stream-based recorder with frame-sequence encoder

- `browser-cli-extension/manifest.json`
  - remove `tabCapture`
  - keep `offscreen`
  - keep any permissions required by current extension runtime

### Python

- `src/browser_cli/drivers/_extension/artifact_actions.py`
  - no contract change expected
  - only small adjustments if metadata or flush responses change

- tests and docs only where behavior/capability wording changes

## Testing

### Automated

Required automated coverage:

- debugger screencast listener tests
  - frame event handling
  - ACK behavior
  - cleanup on detach

- extension video action tests
  - `video-start` establishes recording state
  - `video-stop` stores a deferred artifact
  - `close-tab` flushes `.webm`
  - `workspace-close` / daemon `stop` flush all pending `.webm`

- offscreen behavior tests
  - receive frame sequence
  - finalize encoded `.webm`
  - return base64 payload and metadata

- existing Python driver tests remain green

### Real Chrome Smoke

Required smoke flow:

1. reload unpacked extension
2. `browser-cli reload`
3. `browser-cli status`
4. `browser-cli open <fixture page>`
5. `browser-cli video-start`
6. execute at least one page action
7. `browser-cli video-stop <path>`
8. `browser-cli close-tab`
9. verify `.webm` exists and is playable
10. `browser-cli stop`

## Acceptance Criteria

This change is complete only if all of the following are true:

- `video-start` / `video-stop` work in extension mode on real Chrome
- `video-stop` keeps deferred semantics
- `close-tab` / `workspace-close` / daemon `stop` flush pending `.webm` artifacts
- `video-*` remain in extension required capabilities
- `pytest -q` passes
- `./scripts/check.sh` passes
- real Chrome smoke passes

## Open Tradeoffs

- The output is frame-sampled screencast video, not compositor-perfect screen recording
- No audio capture is attempted
- Frame rate is intentionally conservative for stability

These tradeoffs are acceptable because Browser CLI uses video as a debugging and artifact
delivery tool, not as a high-fidelity screen recorder.
