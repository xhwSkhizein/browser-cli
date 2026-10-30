---
name: browser-cli-explore
description: Use when a Browser CLI task needs site exploration or validation, including one-off extraction and reusable task authoring.
---

# Browser CLI Explore

## Overview

Choose the delivery scope first: a one-off task ends with verified output files
and a concise report; reusable task authoring also captures durable findings in
`task.meta.json`.

## Quick Entry

1. Run `browser-cli status --json`; reuse a healthy runtime. Use `doctor --json`
   for environment diagnosis and the reported recovery guidance for failures.
2. Keep one stable `X_AGENT_ID` across calls. It isolates visible tabs, while
   cookies and storage remain shared. Do not generate a new identity per command.
3. Use `read` for one-shot content; use `open`, focused `snapshot`, and `eval`
   for persistent state.
4. Run dependent same-tab actions sequentially or in a short `batch --file`.
   Batches exclude other browser actions and do not roll back side effects.
5. Prefer text/network conditions and `verify-*` to fixed sleeps. Check business
   status, pagination completion, required fields, and final counts explicitly.

For full extraction, put an arrow function in `extract.js` and run:

```bash
browser-cli eval --file extract.js --output items.json
```

`--file -` reads stdin. The file contains the complete JSON value; stdout returns
only its absolute path, bytes, SHA-256, type, and source in `data.artifact`.
Validate locally and report counts or short samples.
Do not truncate serialized JSON or print cookies and signed URLs into summaries.

All CLI errors are JSON on stdout with nonzero exit codes. Batch step failures
exit 75 even when top-level `ok` is true; inspect `data.success`. Python/Node
high-level `batch()` raises `BATCH_FAILED` and retains partial results in
`payload`. Raw `invoke`/`request` requires an explicit success check. Use
`--result-mode all` when every step result must be saved.

Busy with `execution_state=not_started` is a rejection before execution:
wait for the blocking command before deciding to retry. Timeouts/disconnects
can leave the result unknown; do not replay side effects. A local save error
with `execution_state=completed` means the browser action already ran.
Repair the destination and check page state before deciding whether another
extraction is safe; do not automatically rerun the browser action after a save error.

## Explore and Finish

Keep browser interactions on Browser CLI. Confirm login/profile assumptions,
then choose ref-driven, content-first, lazy-scroll, login-state-first, or
browser-state/network-assisted exploration. Prefer compact `eval` for decisions,
interactive/viewport-scoped `snapshot` for semantic refs, and `html` when the DOM
is the artifact. Widen captures only when evidence is missing.

One-off work ends when the complete requested file is verified and its count,
path, and relevant caveats are reported. Task assets and publishing are unnecessary.

For reusable work, verify observations before capturing them in `task.meta.json`:

- `environment`: site, login, profile and browser assumptions
- `success_path`: validated steps, refs, waits, assertions and artifacts
- `recovery_hints`: retryable steps, alternate paths and stale-ref handling
- `failures`: repeatable failure modes and remedies
- `knowledge`: stable selectors, pagination, loading and output interpretation

Exclude raw logs, transcripts and exploratory dead ends. Stop when the metadata
supports deterministic implementation with `browser-cli-converge`. Skip this
skill for pure API work or refactoring without an evidence gap.
