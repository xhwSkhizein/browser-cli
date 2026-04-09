# Browser CLI V3a Semantic Ref Resolution Design

Date: 2026-04-09
Status: Drafted for review
Repo: `/Users/hongv/workspace/m-projects/browser-cli`

## Summary

`v3a` is not `explore`, and it is not `workflow`.

`v3a` is a prerequisite foundation layer that upgrades Browser CLI refs from
"current snapshot only" markers into recoverable semantic handles.

Today `browser-cli` actions resolve refs by looking up DOM attributes injected by
the latest snapshot. That is sufficient for immediate `snapshot -> action`
interaction, but insufficient for:

- replayable execution scripts
- low-token exploration loops
- stale-ref recovery
- robust reuse across repeated page loads

The purpose of `v3a` is to adopt the semantic ref model from
`bridgic-browser` as the canonical ref design for Browser CLI, then adapt it to
Browser CLI's daemon, tab registry, JSON action contract, and `X_AGENT_ID`
visibility model.

## Scope Correction

The dependency order is now:

1. `v1`: universal rendered page reading
2. `v2`: daemon-backed browser primitives for agents
3. `v3a`: semantic ref resolution
4. `v3b`: explore flows built on semantic refs
5. later: replayable scripts and reusable workflows

This means `v3a` is an internal capability upgrade. It should not be treated as
a new end-user command family.

## Problem Statement

Current Browser CLI ref behavior is centered on
[`snapshot.py`](/Users/hongv/workspace/m-projects/browser-cli/src/browser_cli/browser/snapshot.py)
and
[`service.py`](/Users/hongv/workspace/m-projects/browser-cli/src/browser_cli/browser/service.py):

- snapshot generation walks the DOM directly in page JavaScript
- refs are written to `data-browser-cli-ref`
- actions locate elements by querying that attribute

That design has three hard limits:

1. refs are only reliable inside the current snapshot cycle
2. Browser CLI does not retain enough semantic metadata to reconstruct locators
3. replaying a previously discovered flow would require either a fresh agent
   reasoning pass or brittle hard-coded DOM assumptions

By contrast, `bridgic-browser` treats refs as semantic identifiers derived from
stable element characteristics, then reconstructs Playwright locators from
stored ref metadata. Browser CLI should adopt that semantic core instead of
continuing to build on DOM attribute lookup as the primary ref model.

## Goals

- Make refs reconstructable from semantic metadata, not only from temporary DOM
  attributes.
- Adopt the `bridgic-browser` ref design as the canonical semantic model.
- Preserve Browser CLI's daemon, tabs, JSON responses, and `X_AGENT_ID`
  isolation model.
- Allow ref-based actions to survive DOM re-render within the same page context
  when semantic identity is preserved.
- Provide clear machine-readable failure modes for stale, ambiguous, and missing
  refs.
- Enable future replay scripts to store refs as meaningful handles rather than
  current-DOM markers.
- Keep snapshot output compatible with the current `browser-cli snapshot`
  command while enriching the internal ref registry.

## Non-Goals

- No new public `resolve-ref` command in `v3a`.
- No `explore` command family in `v3a`.
- No workflow DSL in `v3a`.
- No attempt to guarantee ref stability across materially different page
  structures, changed accessible names, or changed iframe structure.
- No cross-domain or cross-site ref portability guarantees.
- No replacement of Browser CLI's daemon or tab model with bridgic's session
  model.

## Options Considered

### 1. Keep current DOM-attribute ref lookup

Advantages:

- minimal engineering change
- good enough for immediate same-snapshot actions

Disadvantages:

- not suitable for replay
- stale refs fail hard
- no semantic recovery path
- forces higher agent token usage during exploration

Rejected.

### 2. Reimplement a simplified semantic resolver inside Browser CLI

Advantages:

- full local control
- can be shaped exactly to Browser CLI's current code

Disadvantages:

- duplicates already-solved work in `bridgic-browser`
- high risk of missing difficult cases such as generic roles, text leaf roles,
  unnamed containers, and iframe scoping
- likely to drift into an inferior partial clone

Rejected.

### 3. Adopt bridgic semantic ref design as the canonical resolver core, then adapt it to Browser CLI runtime

Advantages:

- reuses the most mature part of `bridgic-browser`
- aligns future explore and replay behavior with an already-validated ref model
- avoids inventing a second semantic targeting system

Disadvantages:

- requires upgrading Browser CLI snapshot metadata and registry design
- introduces a larger migration than incremental DOM-attribute tweaks

Chosen direction.

## Chosen Direction

Browser CLI should adopt the `bridgic-browser` semantic ref model as the source
of truth for ref identity and locator reconstruction.

This does **not** mean copying the entire bridgic browser/session runtime into
Browser CLI. It means:

- reusing bridgic-style `RefData`
- reusing bridgic-style locator reconstruction rules
- adapting those capabilities to Browser CLI's daemon-owned browser and
  tab-scoped state

Current DOM attribute lookup may remain as an implementation optimization, but
it must become a fast path only. The semantic resolver becomes the canonical
ref engine.

## Product Shape

Externally, Browser CLI still looks the same:

```bash
browser-cli open https://example.com
browser-cli snapshot
browser-cli click @8d4b03a9
browser-cli fill @6aa217b2 "hello"
```

Internally, the execution path changes from:

`snapshot -> inject DOM ref -> action queries DOM attribute`

to:

`snapshot -> build RefData registry -> action resolves ref through resolver -> action executes locator`

If a DOM attribute fast path exists, it should be:

`fast path -> semantic reconstruction fallback -> explicit failure`

The user contract remains simple. The internal ref contract becomes much richer.

## Core Architecture

### 1. RefData Model

Add a dedicated ref model module, for example:

- `browser_cli.refs.models`

The canonical ref record should include at least:

- `ref`
- `role`
- `name`
- `text_content`
- `nth`
- `tag`
- `interactive`
- `frame_path`
- `parent_ref`
- `playwright_ref`
- `selector_recipe`
- `snapshot_id`
- `page_id`
- `captured_url`
- `captured_at`

`selector_recipe` is diagnostic only. It is useful for debugging and inspection,
but it must not become the only runtime lookup path.

### 2. Snapshot Generator Upgrade

Current snapshot generation should be replaced or substantially upgraded so the
internal snapshot pass produces complete `RefData`, not only lightweight
`refs_summary`.

Recommended approach:

- internalize the relevant bridgic snapshot generation logic under
  `browser_cli.refs.snapshot_generator`
- preserve current Browser CLI snapshot text output format where possible
- store the full ref registry per tab even if stdout only returns tree text plus
  summary

This phase should treat the richer internal data as the main deliverable.

### 3. Tab-Scoped Snapshot Registry

Upgrade tab state to store structured snapshot state instead of only a set of
last-seen ref ids.

Each tab should track:

- `last_snapshot_id`
- `last_snapshot_tree`
- `last_snapshot_created_at`
- `refs_by_id`
- `captured_url`
- `captured_title`

This registry belongs to the tab because Browser CLI already centers action
execution on the current agent-visible active tab.

### 4. Resolver Layer

Add a dedicated resolver module, for example:

- `browser_cli.refs.resolver`

Responsibilities:

- parse refs from command arguments
- retrieve `RefData` from the current tab registry
- build the correct page or frame scope
- reconstruct a Playwright locator from semantic metadata
- return structured resolution outcomes

The resolver should be the only component allowed to translate ref ids into
runtime locators.

### 5. Action-Layer Integration

All ref-based actions in
[`service.py`](/Users/hongv/workspace/m-projects/browser-cli/src/browser_cli/browser/service.py)
must stop querying `data-browser-cli-ref` directly.

Instead they should call a shared resolver path used by:

- `click`
- `double-click`
- `hover`
- `focus`
- `fill`
- `select`
- `options`
- `check`
- `uncheck`
- `scroll-to`
- `drag`
- `upload`
- `eval-on`
- `verify-state`
- `verify-value`

The browser service remains the orchestration layer. It should not embed ref
reconstruction rules inline.

## Resolution Pipeline

The recommended resolution order is:

1. parse and validate ref syntax
2. load `RefData` from the active tab's registry
3. establish frame scope from `frame_path`
4. try semantic reconstruction using bridgic-style rules
5. if locator resolves cleanly, return it
6. if ref metadata is missing, return `REF_NOT_FOUND`
7. if metadata exists but the element can no longer be reconstructed, return
   `STALE_REF`
8. if reconstruction yields multiple plausible matches without deterministic
   disambiguation, return `AMBIGUOUS_REF`

An optional DOM-attribute fast path is acceptable, but only under these rules:

- it is purely an optimization
- it is not required for correctness
- the semantic path must work when the DOM marker is absent

## Semantic Reconstruction Rules

Browser CLI should directly reuse bridgic's broad reconstruction strategy:

- scope first by `frame_path`
- prefer `role + exact name` for semantic roles
- use role-constrained text matching where role semantics are weak
- use `parent_ref` and child anchors for unnamed structural nodes
- apply `nth` only where the key space matches the original disambiguation logic
- preserve special treatment for text-leaf roles and structural-noise roles

The intent is not to invent new targeting heuristics. The intent is to reuse the
targeting heuristics already validated in `bridgic-browser`.

## Failure Semantics

`v3a` must strengthen error semantics instead of silently falling back to fuzzy
guessing.

Recommended machine-readable outcomes:

- `REF_NOT_FOUND`
  The ref id is not known in the current tab registry.

- `STALE_REF`
  The ref is known, but the element cannot be reconstructed in the current page
  state.

- `AMBIGUOUS_REF`
  The ref metadata points to more than one plausible match and the resolver
  cannot deterministically choose one.

- `NO_SNAPSHOT_CONTEXT`
  A ref-based action was attempted before any snapshot state was captured for
  the tab.

The CLI should continue surfacing short human-readable errors while keeping the
JSON error code stable.

## Interaction with Future Explore and Replay

`v3a` is the foundation for later phases.

After `v3a`, an explore process can:

- snapshot once
- use refs as low-token handles during iterative trial and error
- keep a stable semantic registry in the daemon
- export replay steps that reference recoverable refs rather than transient DOM
  markers

This is the point of the phase. `v3a` makes future replay scripts viable without
requiring the agent to re-identify every target from scratch on every run.

## Testing Strategy

Testing should be expanded in four layers.

### 1. RefData Unit Tests

- deterministic ref generation
- frame-path-aware disambiguation
- `nth` behavior for duplicate role/name groups
- parse and normalization tests

### 2. Resolver Unit Tests

- `role + exact name` reconstruction
- text-leaf reconstruction
- unnamed structural-node reconstruction via `parent_ref`
- iframe-scoped reconstruction
- ambiguity and stale-ref outcomes

### 3. Integration Tests

Use local fixture pages to validate:

- ref survives DOM re-render when semantic identity remains the same
- ref fails with `STALE_REF` when semantics materially change
- iframe-contained refs resolve correctly
- generic/group/text edge cases resolve correctly
- all ref-based daemon actions work through the resolver rather than DOM
  attribute lookup alone

### 4. Regression Guard

Keep a parity-oriented test that ensures Browser CLI's semantic ref behavior does
not regress below the adopted bridgic capability envelope for supported action
types.

## Migration Strategy

This phase should be implemented as an internal migration, not as a public
breaking change to command names.

Recommended sequence:

1. introduce `RefData` and snapshot registry modules
2. internalize/adapt bridgic snapshot generation
3. internalize/adapt bridgic locator reconstruction
4. switch one ref-based action path onto the resolver
5. switch the remaining ref-based actions
6. leave DOM marker lookup only as optional optimization
7. remove obsolete direct-lookup assumptions from the tab registry and service

The migration should be complete before `v3b explore` begins.

## Acceptance Criteria

`v3a` is complete when all of the following are true:

- Browser CLI stores full semantic ref metadata per tab
- ref-based actions no longer depend on DOM markers as the only lookup method
- locator reconstruction follows bridgic-style semantic rules
- stale and ambiguous refs fail with explicit structured errors
- the existing action surface remains unchanged for callers
- local integration tests prove semantic reconstruction on real pages served from
  the fixture harness
- Browser CLI is ready for an explore phase that emits replayable ref-based
  execution steps
