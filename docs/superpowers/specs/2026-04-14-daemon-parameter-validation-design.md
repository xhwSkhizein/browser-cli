# Browser CLI Daemon Parameter Validation Design

Date: 2026-04-14
Status: Drafted for review
Repo: `browser-cli`

## Summary

This design standardizes user-input numeric parsing in the daemon request
handler layer so malformed command arguments return stable `INVALID_INPUT`
errors instead of leaking `INTERNAL_ERROR` responses.

The change is intentionally scoped to `src/browser_cli/daemon/app.py`, where
daemon request arguments are converted from `request.args` into typed Python
values before browser operations are called.

The design introduces shared parsing helpers for integers and floats, then
applies them across all user-facing numeric argument entrypoints, including:

- mouse coordinate commands
- resize commands
- wait and timeout commands
- other handlers that currently perform raw `int(...)` or `float(...)`
  conversions on request arguments

## Problem Statement

The daemon request layer currently mixes two styles of input handling:

- some fields use explicit validation helpers such as `_require_str()`
- some numeric fields are converted inline with `int(request.args.get(...))` or
  `float(request.args.get(...))`

That inconsistency creates release-quality problems:

1. missing or malformed numeric arguments can raise raw `TypeError` or
   `ValueError`
2. those exceptions bypass user-input semantics and surface as
   `INTERNAL_ERROR`
3. clients receive traceback-shaped failures for what should be ordinary usage
   errors

This is especially visible in coordinate-heavy commands such as
`mouse-click`, `mouse-move`, and `mouse-drag`, but the underlying issue is
broader: daemon handlers are not consistently responsible for normalizing and
validating user input before calling the service layer.

## Goals

- Make malformed numeric command arguments return `InvalidInputError`.
- Keep missing-field errors explicit and field-oriented.
- Keep range or command-specific constraints in the relevant handler.
- Standardize numeric parsing behavior across daemon handlers.
- Preserve successful command behavior.
- Add regression tests that prove malformed inputs no longer surface as
  `INTERNAL_ERROR`.

## Non-Goals

- This design does not change browser service or driver method signatures.
- This design does not redesign non-numeric argument validation.
- This design does not introduce a new daemon transport or error envelope.
- This design does not move CLI/daemon parsing logic into lower layers.

## Chosen Direction

Browser CLI should treat daemon handlers as the single normalization layer for
user-supplied request arguments.

Numeric parsing should be centralized in helper methods on
`BrowserDaemonApp`, then reused by every handler that accepts numeric input.

The error model should be:

- missing required field -> field-level message
- malformed numeric value -> field-level type message
- command-specific range/semantic violation -> handler-level constraint message

This preserves good diagnostics without conflating internal bugs with user
input errors.

## Options Considered

### 1. Shared daemon parsing helpers

Add shared helper methods such as `_require_int()` and `_require_float()` to
`BrowserDaemonApp`, then migrate handlers to use them.

Advantages:

- keeps parsing semantics in one place
- improves consistency across commands
- makes future handlers harder to regress
- preserves lower-layer boundaries

Disadvantages:

- requires touching several handlers in one pass

Chosen direction.

### 2. Per-handler local try/except blocks

Patch only the currently failing handlers by catching `TypeError` and
`ValueError` inline.

Advantages:

- smallest initial patch

Disadvantages:

- duplicates parsing logic
- easy for future handlers to drift
- does not create a durable validation pattern

Rejected.

### 3. Outer exception remapping

Catch numeric conversion failures at the top of `execute()` and translate them
to `InvalidInputError`.

Advantages:

- broad coverage with fewer edits

Disadvantages:

- weak context for error messages
- risks converting genuine internal bugs into usage errors
- blurs responsibility between handler code and top-level execution flow

Rejected.

## Layering Rule

The parsing and validation change must stay in:

- `src/browser_cli/daemon/app.py`

This file owns user-facing daemon argument normalization and is the correct
layer for converting request payloads into typed inputs.

The following layers should remain unchanged in responsibility:

- `browser_service`: consumes already-validated typed values
- drivers: execute browser behavior, not user-input parsing
- transport: carries payloads, not validation policy

## Helper Contract

`BrowserDaemonApp` should add shared helper methods for numeric parsing.

At minimum:

- `_require_int(args, key)`
- `_optional_int(args, key)`
- `_require_float(args, key)`
- `_optional_float(args, key)`

Optional range-specific helpers may be added only if they reduce duplication
without obscuring command-level semantics.

### Error Messages

The helpers should produce field-level diagnostics:

- missing required integer:
  `x is required.`
- invalid integer:
  `x must be an integer.`
- missing required float:
  `timeout is required.`
- invalid float:
  `timeout_seconds must be a number.`

Helpers should not enforce command-specific range rules such as positive sizes
or non-negative counts. Those remain the handler's responsibility.

## Handler Coverage

The implementation should cover every handler in `daemon/app.py` that currently
does direct numeric parsing from `request.args`.

This includes two categories.

### Category 1: Unsafe Inline Parsing

These handlers currently risk surfacing internal failures and must be migrated:

- `mouse-click`
- `mouse-move`
- `mouse-drag`
- any other handler using direct `int(request.args.get(...))` or
  `float(request.args.get(...))` without protective validation

### Category 2: Already-Constrained Commands With Duplicated Parsing

These handlers should also be moved to the shared helpers so behavior stays
consistent:

- `resize`
- `scroll`
- timeout-based `wait` handlers
- network wait handlers
- verify handlers with timeout parameters

The exact list should be derived from the current `daemon/app.py`
implementation rather than guessed from public docs.

## Error Semantics

The resulting behavior should be:

- missing numeric fields return `INVALID_INPUT`
- malformed numeric fields return `INVALID_INPUT`
- command-specific range checks continue returning `INVALID_INPUT`
- internal daemon failures unrelated to user input continue returning
  `INTERNAL_ERROR` or other existing typed errors

This distinction matters because clients should be able to tell whether they
need to fix the request or retry the system.

## Testing Strategy

This change needs regression tests at the daemon application layer.

### Required Tests

Add tests that execute `BrowserDaemonApp.execute()` for malformed numeric
requests and assert:

- `ok` is `False`
- `error_code` is `INVALID_INPUT`
- the error message identifies the bad field or violated command constraint

### Regression Cases

At least one test should explicitly lock the previously broken behavior:

- `mouse-click` without `x`
- or another command that previously returned `INTERNAL_ERROR`

The test should prove the response now returns `INVALID_INPUT` instead.

### Success-Path Safety

Existing success-path tests should remain unchanged unless a handler signature
or public contract is actually modified.

If needed, add a small success-path sanity test for one representative command
that now uses the shared helpers.

## Files Expected To Change

Primary files:

- `src/browser_cli/daemon/app.py`
- `tests/unit/test_daemon_server.py` or `tests/unit/test_daemon_browser_service.py`
  only if existing coverage belongs there
- a new or expanded unit test file for daemon app request validation

No architecture changes are expected beyond request-handler input normalization.

## Risks

- over-broad top-level exception remapping could hide real bugs
- inconsistent migration could leave some handlers on old parsing behavior
- helper overreach could mix field parsing with command semantics

The design controls these risks by:

- keeping parsing helpers narrow
- keeping command-specific range rules in handlers
- testing malformed requests through `BrowserDaemonApp.execute()`

## Acceptance Criteria

This design is complete when:

- malformed numeric daemon inputs no longer return `INTERNAL_ERROR`
- missing numeric arguments return field-level `InvalidInputError` messages
- command-specific numeric constraints still return explicit usage errors
- all direct user-facing numeric conversions in `daemon/app.py` are routed
  through shared helper logic
- regression tests lock the new error behavior
