# Task Modes

Choose the primary task mode before exploring. Start with one mode and switch
only when evidence demands it.

## Content-First

Use when:

- the goal is extracting rendered text, tables, cards, or form results
- the page meaning is visible in DOM semantics

Prefer:

- `snapshot`
- semantic refs
- `click`, `fill`, `wait`, `html`

Avoid:

- overusing `eval` when refs and rendered HTML already prove the path

## Browser-State-First

Use when:

- success depends on signed URLs, browser-generated tokens, cookies, storage, or performance state
- the page is easier to reason about through browser state than visible DOM
- anti-bot behavior makes direct replay fragile

Prefer:

- `open`
- `eval`
- `performance` entries
- cookies and storage capture
- Python replay with the validated browser context

Avoid:

- assuming `network` capture already gives you response bodies
- defaulting to semantic refs when the real signal lives in browser state

This was the right mode for the Douyin download task.

## Login-State-First

Use when:

- the task depends on an existing logged-in profile
- the main risk is session validity, not page interaction mechanics

Prefer:

- verify login state immediately
- record profile assumptions in metadata
- stop early if the needed session is absent

Avoid:

- exploring deep flows before proving the profile is usable

## Scroll-First

Use when:

- content appears only after incremental loading
- the main difficulty is stabilization rather than interaction

Prefer:

- bounded scroll loops
- explicit stability checks
- artifacts that record the stabilization history

Avoid:

- open-ended scrolling with no stop rule

## Response-Body Gate

If the task requires direct access to response bodies, decide that up front.

- If `browser-cli` already exposes the response body you need, use it.
- If it only exposes request metadata, either find a stable browser-state-first fallback or stop and confirm the runtime gap.

Do not discover this after a long exploration loop if you can prove it early.
