# Browser CLI Persistent Startup Page Reuse Design

Date: 2026-04-14
Status: Drafted for review
Repo: `browser-cli`

## Summary

Browser CLI currently starts its managed Chrome backend with Playwright's
persistent context API, then immediately closes every page already present in
that context. On this machine and in a minimal local reproduction, that leaves
the context unable to create a new page: later calls to `new_page()` fail with
`Target.createTarget: Failed to open a new tab`.

This spec changes Browser CLI's browser-service behavior so startup pages in a
persistent context are treated as reusable blank workspace pages instead of
being eagerly closed. `new_tab()` and `read_page()` will first try to claim a
safe startup blank page, and only call `new_page()` when no reusable startup
page is available.

## Problem Statement

The current startup flow in `src/browser_cli/browser/service.py` does this:

1. launch a persistent Chrome context
2. add init script if needed
3. close all existing pages in `context.pages`
4. later create tabs with `context.new_page()`

That sequence is unsafe for the managed-profile backend. In a persistent Chrome
context, Playwright may create one startup `about:blank` page. If Browser CLI
closes that last page, later attempts to create a new page can fail at the
protocol layer.

The concrete effect is:

- `browser-cli reload` can succeed while leaving a daemon that looks healthy
- the first `browser-cli read ...` or other tab-creating action fails
- daemon logs show `BrowserContext.new_page: Protocol error (Target.createTarget): Failed to open a new tab`

This is not a user-environment setup problem. It is a browser-service lifecycle
bug in Browser CLI's managed Playwright path.

## Goals

- Keep the persistent managed-profile backend able to open tabs after startup.
- Reuse safe startup blank pages instead of eagerly destroying them.
- Preserve the public CLI and daemon contracts.
- Keep the change contained to the browser-service implementation and tests.
- Add regression coverage for the reproduced failure mode.

## Non-Goals

- No redesign of daemon lifecycle or action contracts.
- No change to extension-driver semantics.
- No change to agent tab-ownership rules.
- No attempt to solve extension listener port conflicts in this change.
- No general page pooling feature beyond safe startup-page reuse.

## Options Considered

### 1. Stop closing startup pages and reuse blank ones

Track startup pages present when the persistent context is launched. When a
command needs a page, first try to claim one of those pages if it is still open
and still blank; otherwise fall back to `new_page()`.

Advantages:

- directly fixes the reproduced failure mode
- keeps public behavior unchanged
- minimal surface area
- easy to verify with targeted tests

Disadvantages:

- adds a small amount of page-lifecycle state to `BrowserService`
- requires careful rules for when a startup page is considered reusable

Chosen.

### 2. Keep closing startup pages but immediately recreate one placeholder page

After closing existing pages, call `new_page()` once during startup so the
context always retains a page.

Advantages:

- small behavioral change
- simple mental model

Disadvantages:

- depends on `new_page()` already working after the close sequence, which is
  exactly what fails
- does not address the root cause

Rejected.

### 3. Special-case `read_page()` only

Teach `read_page()` to reuse an existing blank startup page, but leave
`new_tab()` unchanged.

Advantages:

- smaller first patch if only `read` mattered

Disadvantages:

- leaves `new_tab()` and any other page-creation path inconsistent
- preserves a latent bug outside `read`

Rejected.

## Chosen Direction

Browser CLI should preserve startup pages in a persistent Chrome context and
reuse them when they are safe.

The browser service will:

- record pages already present after `launch_persistent_context(...)`
- stop closing them during startup
- treat startup pages as reusable only if they are still open and still blank
- let `new_tab()` and `read_page()` claim a reusable startup page before
  calling `context.new_page()`
- remove a startup page from the reusable pool as soon as Browser CLI assigns
  it to a page id

This keeps the fix local to the browser service and avoids any CLI or daemon
contract churn.

## Architecture And Boundaries

### Browser Service

Relevant file:

- `src/browser_cli/browser/service.py`

Responsibilities after this change:

- own startup-page tracking state
- decide whether a startup page is reusable
- provide one internal page-acquisition path used by both `new_tab()` and
  `read_page()`
- clear startup-page state during shutdown

This remains the correct ownership boundary because the failure is caused by
Playwright persistent-context lifecycle behavior, not by daemon routing or CLI
input handling.

### Daemon Layer

Relevant files:

- `src/browser_cli/daemon/browser_service.py`
- `src/browser_cli/daemon/app.py`

Responsibilities do not change. The daemon still asks the active driver to open
or read a page. The fix must remain invisible to the daemon JSON contract.

### Driver Layer

Relevant files:

- `src/browser_cli/drivers/playwright_driver.py`
- `src/browser_cli/drivers/base.py`

No contract changes. Playwright driver behavior improves only because the
underlying browser service becomes safe to use after startup.

## Detailed Behavior

### Startup

After `launch_persistent_context(...)`, Browser CLI must no longer close every
page in `self._context.pages`.

Instead it should snapshot those pages into a reusable-startup-page pool.

### Page Acquisition

Both `new_tab()` and `read_page()` should use one internal helper that:

1. checks the reusable-startup-page pool
2. picks the first page that is:
   - not closed
   - at `about:blank` or equivalent blank startup state
3. removes that page from the reusable pool
4. returns it for normal Browser CLI page registration
5. falls back to `self._context.new_page()` only when no reusable startup page
   exists

This helper should not attempt broad page heuristics or workspace-window logic.
It is only for safe reuse of known startup pages created by the persistent
context itself.

### Shutdown And Cleanup

`stop()` must clear startup-page tracking state together with the existing page,
snapshot, and observer state.

### Failure Handling

If startup-page reuse fails unexpectedly, Browser CLI should fall back to
`new_page()` and preserve the original failure if both paths fail. The new logic
must not mask real Playwright or Chrome errors behind silent retries.

## Testing Strategy

Add targeted unit coverage around the browser service:

- startup does not close the initial persistent-context page
- `new_tab()` can claim a reusable startup blank page
- `read_page()` can claim a reusable startup blank page
- non-blank startup pages are not reused
- startup-page tracking is cleared on `stop()`

Also add a focused reproduction-oriented test at the service seam:

- simulate a persistent context with one startup blank page where `new_page()`
  would fail after that page is closed
- verify the new startup-page reuse path avoids the `Target.createTarget`
  failure

## Risks And Mitigations

- Risk: Browser CLI may accidentally reuse a page that is no longer blank.
  Mitigation: only reuse tracked startup pages that are still open and still at
  a blank URL.

- Risk: State may drift if a tracked startup page is externally closed.
  Mitigation: validate page liveness at claim time and drop closed pages from
  the pool.

- Risk: Separate extension-port startup failures could be mistaken for this
  bug.
  Mitigation: keep this spec limited to persistent-page lifecycle behavior and
  leave extension listener port handling unchanged.

## Validation

After implementation:

- run the targeted browser-service tests for startup-page reuse
- run a local reproduction equivalent to the observed failure
- verify `browser-cli reload` followed by `browser-cli read https://example.com`
  no longer fails with `Target.createTarget`
- run `scripts/lint.sh`
- run `scripts/test.sh`
- run `scripts/guard.sh`
