# Browser CLI Task Runtime Read Unification Design

Date: 2026-04-14
Status: Drafted for review
Repo: `browser-cli`

## Summary

Browser CLI currently exposes two Python-side runtime concepts for page reading:

- `browser_cli.runtime.read_runner` owns one-shot `read` orchestration for the
  CLI
- `browser_cli.task_runtime` owns the public Python client used by `task.py`
  and the automation service

That split has caused capability drift. The CLI `read` path supports
Chrome-environment discovery, fallback profile reporting, and a complete
one-shot `read-page` orchestration path, while `browser_cli.task_runtime` does
not expose an equivalent `read` operation.

This spec removes that split. `browser_cli.task_runtime` becomes the only
public Python runtime surface. One-shot `read` becomes a first-class capability
of `BrowserCliTaskClient`, and both `Flow.read()` and `browser-cli read` reuse
the same implementation.

## Problem Statement

Today the Python runtime surface is inconsistent:

- `browser_cli.runtime.read_runner` implements one-shot `read`
- `BrowserCliTaskClient` does not provide `read`
- `Flow` therefore cannot provide a native `read` helper
- the automation service, which already uses `BrowserCliTaskClient`, cannot rely
  on the same `read` behavior as the CLI

This causes several concrete problems:

- Python users must compose `open()` plus `snapshot()` or `html()` manually
  instead of calling a single basic operation
- Chrome-environment discovery is trapped inside the CLI-oriented
  `read_runner` path
- fallback profile metadata is not available through the public Python runtime
- the repo documents two overlapping runtime concepts, making future drift more
  likely

The real issue is not missing convenience methods. The issue is that the public
Python runtime contract is split across two packages with different behavior.

## Goals

- Make `browser_cli.task_runtime` the only public Python runtime surface.
- Remove `browser_cli.runtime` as a public package.
- Add first-class one-shot `read` support to `BrowserCliTaskClient`.
- Ensure `Flow.read()` and CLI `read` use the exact same read orchestration.
- Preserve the existing daemon-side `read-page` contract.
- Preserve current user-visible CLI behavior for fallback profile reporting and
  empty-content failures.
- Update tests, docs, and agent navigation so future work follows the unified
  path.

## Non-Goals

- No daemon-side `read-page` contract redesign.
- No expansion of the `read` feature beyond the current CLI contract in this
  change.
- No package rename from `task_runtime` to `runtime`.
- No attempt to redesign unrelated `task_runtime` helper APIs.
- No behavioral divergence between CLI `read` and Python `read`.

## Options Considered

### 1. Move read orchestration into `task_runtime`

Add `BrowserCliTaskClient.read(...)`, move the shared one-shot orchestration
under `browser_cli.task_runtime`, and make `Flow.read()` plus CLI `read` call
that path.

Advantages:

- creates one public Python runtime surface
- fixes the immediate capability drift
- keeps daemon and CLI contracts stable
- lets automation inherit the same read behavior automatically

Disadvantages:

- makes `task_runtime` slightly broader than a pure action wrapper
- requires docs, tests, and imports to be updated together

Chosen.

### 2. Keep `task_runtime` public but add a dedicated shared internal read module

Add a dedicated internal shared module for read orchestration, then have both
`BrowserCliTaskClient` and CLI `read` depend on it.

Advantages:

- keeps the client class thinner
- isolates one-shot read logic into a dedicated unit

Disadvantages:

- still leaves a second conceptual runtime layer to explain
- increases the risk that future work bypasses the public runtime surface again

Rejected as the primary structure. A small internal helper module inside
`task_runtime` is still acceptable as part of option 1.

### 3. Rename `task_runtime` to `runtime`

Treat the unification as a package rename and move all public runtime concerns
under `browser_cli.runtime`.

Advantages:

- appears more uniform by name

Disadvantages:

- solves naming before solving ownership
- greatly expands migration scope across imports, docs, tests, and guidance
- risks replacing one ambiguous runtime concept with another broader one

Rejected.

## Chosen Direction

`browser_cli.task_runtime` should remain the package name and become the only
public Python runtime API.

The new contract is:

- `BrowserCliTaskClient.read(...)` is the canonical one-shot page-read API
- `Flow.read(...)` is a thin wrapper around `BrowserCliTaskClient.read(...)`
- `browser-cli read` uses the same implementation and keeps only CLI-specific
  duties
- `browser_cli.runtime` is removed

This keeps the public runtime surface singular without forcing a broader
package rename.

## Architecture And Boundaries

### Public Python Runtime

`browser_cli.task_runtime` owns the public Python runtime contract.

Relevant modules:

- `src/browser_cli/task_runtime/client.py`
- `src/browser_cli/task_runtime/flow.py`
- `src/browser_cli/task_runtime/__init__.py`

Responsibilities:

- expose `BrowserCliTaskClient.read(...) -> ReadResult`
- expose `Flow.read(...) -> ReadResult`
- export the stable runtime-facing models needed by Python users

### Internal Read Orchestration

The one-shot `read` implementation should live under `task_runtime`, either in
`client.py` or a small internal helper such as `task_runtime/read.py`.

Responsibilities:

- build the `read-page` request arguments
- detect whether daemon startup needs Chrome-environment discovery
- include Chrome-environment data when the daemon is not already running
- translate daemon payloads into `ReadResult`
- raise `EmptyContentError` when the body is empty after trimming

This is the shared core implementation for Python and CLI consumers.

### CLI Layer

`src/browser_cli/commands/read.py` remains a user-interface layer only.

Responsibilities:

- normalize the input URL
- construct the public read request
- call into `BrowserCliTaskClient.read(...)`
- render `ReadResult.body`
- print fallback-profile guidance to stderr when appropriate

The CLI command must stop owning any private one-shot read orchestration.

### Daemon Layer

The daemon remains unchanged in role.

Relevant modules:

- `src/browser_cli/daemon/client.py`
- `src/browser_cli/daemon/app.py`
- `src/browser_cli/daemon/browser_service.py`

Responsibilities remain:

- daemon lifecycle and transport
- `read-page` request handling
- actual browser read execution

This change unifies the Python entrypoint, not the daemon contract.

## API Shape

### `BrowserCliTaskClient.read`

Add:

```python
def read(
    self,
    url: str,
    *,
    output_mode: str = "html",
    scroll_bottom: bool = False,
) -> ReadResult: ...
```

This method should match the current CLI `read` contract and no more.

Supported behavior:

- `url`
- `output_mode="html"` or `"snapshot"`
- `scroll_bottom`

Not part of this change:

- extra timeout options
- generalized waiting policies
- a daemon JSON passthrough mode

### `ReadResult`

The public result model should remain explicit and typed:

```python
@dataclass(slots=True)
class ReadResult:
    body: str
    used_fallback_profile: bool = False
    fallback_profile_dir: str | None = None
    fallback_reason: str | None = None
```

This matches current CLI-visible behavior while keeping the Python API stable
and more structured than a `dict`.

### `Flow.read`

Add a thin convenience method:

```python
def read(
    self,
    url: str,
    *,
    output_mode: str = "html",
    scroll_bottom: bool = False,
) -> ReadResult: ...
```

`Flow.read` should not own any orchestration logic of its own.

## Data Flow

### CLI Read

The CLI flow becomes:

1. `browser-cli read <url>`
2. `commands/read.py` normalizes the URL
3. `BrowserCliTaskClient.read(...)`
4. shared `task_runtime` read orchestration
5. `send_command("read-page", ...)`
6. daemon `read-page` handler
7. browser-service `read_page(...)`
8. `ReadResult` returned to the CLI
9. CLI renders `body` and prints fallback-profile guidance if needed

### Task And Automation Read

The task and automation flow becomes:

1. task code calls `flow.read(...)` or `client.read(...)`
2. `Flow.read(...)` delegates to `BrowserCliTaskClient.read(...)`
3. shared `task_runtime` read orchestration
4. `send_command("read-page", ...)`
5. daemon `read-page` handler
6. browser-service `read_page(...)`
7. `ReadResult` returned to the caller

The result is that CLI, tasks, and automations all share the same Python-side
read behavior.

## Migration Plan

### Code Movement

- move the `ReadRequest` / `ReadResult` / orchestration logic out of
  `src/browser_cli/runtime/read_runner.py`
- place the shared implementation under `src/browser_cli/task_runtime/`
- add `BrowserCliTaskClient.read(...)`
- add `Flow.read(...)`
- update `src/browser_cli/commands/read.py` to use the unified path
- remove `src/browser_cli/runtime/read_runner.py`
- remove `src/browser_cli/runtime/` entirely if it no longer contains any
  retained ownership

### Public Package Contract

After the change:

- `browser_cli.task_runtime` is the only public Python runtime package
- `browser_cli.runtime` is not documented or imported as a public surface

This is an intentional cleanup, not a compatibility-preserving alias layer.

## Error Handling

The unified read path should preserve current behavior:

- empty rendered output still raises `EmptyContentError`
- daemon lifecycle and socket failures still flow through the existing daemon
  client error types
- profile-discovery failures still surface through the existing error model
- CLI-only stderr messaging remains in `commands/read.py`

The runtime layer returns structured data and raises runtime errors. The CLI
layer remains responsible for human-facing presentation.

## Testing And Validation

### Unit Tests

Add or update tests for:

- `BrowserCliTaskClient.read(...)` request construction
- Chrome-environment injection when the daemon is not already running
- `ReadResult` mapping from daemon payloads
- empty-body failure behavior
- `Flow.read(...)` delegating without adding extra logic
- CLI `read` continuing to normalize URLs, render output, and report fallback
  profile information to stderr

### Integration Tests

Replace or adapt the current `ReadRunner` integration tests so they validate the
new unified entrypoint, likely through `BrowserCliTaskClient.read(...)`.

Key scenarios:

- capture HTML from a dynamic fixture
- capture snapshot output from a static fixture
- `scroll_bottom=True` loads more content without leaking tabs

### Full Validation

Run the standard repository validation flow:

- `scripts/lint.sh`
- `scripts/test.sh`
- `scripts/guard.sh`

## Documentation And Guidance Updates

Update the durable guidance surfaces in the same change:

- `AGENTS.md`
- task/runtime documentation that still points agents to
  `src/browser_cli/runtime/read_runner.py`
- examples that should now rely on `BrowserCliTaskClient.read(...)` or
  `Flow.read(...)`

The key documentation rule after this change is:

- Python-side runtime logic belongs in `browser_cli.task_runtime`
- CLI `read` is a command surface, not a separate runtime implementation

## Success Criteria

This work is complete when all of the following are true:

- `browser_cli.runtime` is removed as a public Python runtime package
- `BrowserCliTaskClient.read(...)` is the canonical one-shot read API
- `Flow.read(...)` and CLI `read` use the same Python-side implementation
- the automation service inherits the same read behavior through
  `BrowserCliTaskClient`
- tests cover the unified path instead of the old `ReadRunner` path
- docs and agent navigation no longer describe split runtime ownership
