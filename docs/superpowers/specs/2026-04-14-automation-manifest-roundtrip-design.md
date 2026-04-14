# Automation Manifest Round-Trip Design

Date: 2026-04-14
Status: Drafted for review
Repo: `browser-cli`

## Summary

This design unifies Browser CLI's automation manifest semantics across
`publish`, `import`, `export`, `inspect`, and persistence.

The goal is semantic consistency, not raw TOML text preservation.

That means:

- supported manifest fields must keep the same meaning across all round-trip
  paths
- published snapshot manifests may rewrite paths into snapshot/runtime context
- exported manifests may normalize defaults and formatting
- no supported field may be silently dropped, renamed, or interpreted
  differently on one path than another

## Problem Statement

Browser CLI already has the pieces for automation packaging and inspection, but
the field mapping logic is duplicated across several surfaces:

- `publisher.py` renders snapshot manifests
- `api/server.py` converts between API payloads, persisted definitions, and
  exported TOML
- `commands/automation.py` assembles inspect payloads
- `models.py` contains only part of the manifest-to-persistence mapping

That duplication creates release-risking drift:

- supported fields can survive one path but disappear on another
- `snapshot_config` and `live_config` can expose similar data with different
  shapes
- publish and export can each define their own idea of the canonical manifest
- future field additions require hand-editing multiple projection sites

For the first public release, Browser CLI needs one stable semantic model for
automation configuration.

## Goals

- Make `publish`, `import`, `export`, `inspect`, and persistence agree on one
  supported manifest field set.
- Preserve supported field semantics across all round-trip paths.
- Keep `snapshot_config` and `live_config` separate in `inspect`, but render
  them with the same config-view shape.
- Allow path normalization into snapshot or runtime context without treating it
  as semantic drift.
- Reduce duplicated projection logic so future manifest fields are harder to
  implement inconsistently.

## Non-Goals

- No raw TOML text preservation guarantee.
- No unknown-field passthrough guarantee.
- No change to automation runtime execution behavior in this work.
- No third configuration truth source beyond snapshot manifests and persisted
  live state.
- No new public automation subcommands.

## Chosen Direction

Browser CLI introduces a shared automation projection layer that owns the
supported manifest semantics and the stable conversions between internal models
and user-facing views.

Two existing truths remain:

- immutable snapshot manifest under
  `~/.browser-cli/automations/<automation-id>/versions/<version>/automation.toml`
- current live persisted automation definition in the automation service

The new projection layer does not replace those truths. It ensures both are
encoded, decoded, and rendered through one semantic contract.

## Options Considered

### 1. Shared Projection Layer

Create one reusable mapping layer for manifest, persistence, export, publish,
and inspect.

Advantages:

- one semantic contract for supported fields
- fewer projection sites to keep in sync
- easier to add future supported fields safely

Disadvantages:

- requires touching several existing modules
- moves some logic out of current helpers

Chosen direction.

### 2. Surface-By-Surface Fixes

Patch `publish`, `export`, `inspect`, and import independently.

Advantages:

- smaller immediate edits

Disadvantages:

- preserves duplicated mapping logic
- makes future drift likely
- keeps config-view inconsistency risk high

Rejected.

### 3. Persist Raw Manifest Blobs

Store raw TOML or parsed source payloads as an additional truth source.

Advantages:

- closer to text preservation

Disadvantages:

- conflicts with the chosen semantic-consistency goal
- introduces redundant truth sources
- adds release-window scope without improving core user semantics

Rejected.

## Canonical Supported Field Set

This design standardizes the supported manifest fields that every round-trip
path must understand and preserve semantically:

- `automation.id`
- `automation.name`
- `automation.description`
- `automation.version`
- `task.path`
- `task.meta_path`
- `task.entrypoint`
- `inputs`
- `schedule.mode`
- `schedule.timezone`
- normalized schedule payload fields beyond `mode` and `timezone`
- `outputs.artifact_dir`
- `outputs.result_json_path`
- `outputs.stdout`
- `hooks.before_run`
- `hooks.after_success`
- `hooks.after_failure`
- `runtime.retry_attempts`
- `runtime.retry_backoff_seconds`
- `runtime.timeout_seconds`
- `runtime.log_level`

Unknown field preservation is explicitly out of scope.

## Semantic Normalization Rules

This design uses semantic equality rather than textual equality.

Allowed normalization:

- rewrite `task.path` and `task.meta_path` into snapshot-local paths during
  publish
- rewrite `outputs.artifact_dir` and `outputs.result_json_path` into snapshot
  or runtime output locations
- render explicit defaults when generating a manifest from persistence or
  generated defaults
- normalize schedule payload ordering or TOML formatting

Disallowed drift:

- silent loss of a supported field
- renaming a supported field on one path
- changing the meaning of `None`, empty, or default values across surfaces
- exposing different config-view field sets for snapshot vs live inspect

## Architecture

### Existing Models

The existing dataclasses remain the core semantic models:

- `AutomationManifest` is the file-backed manifest semantic model
- `PersistedAutomationDefinition` is the live automation-service model

### New Shared Projection Layer

Add a shared projection module at:

`src/browser_cli/automation/projections.py`

This module owns the stable conversions among:

- `AutomationManifest -> PersistedAutomationDefinition`
- `PersistedAutomationDefinition -> manifest sections / TOML-ready structure`
- `AutomationManifest -> snapshot manifest sections`, with path remapping
- `AutomationManifest -> inspect config view`
- `PersistedAutomationDefinition -> inspect config view`

This module becomes the single semantic mapping authority for supported fields.

### Ownership Boundaries

- `models.py` keeps dataclass definitions. Projection authority moves to the
  shared projection layer.
- `publisher.py` delegates snapshot manifest construction to the shared
  projection layer.
- `api/server.py` delegates import/export field projection to the shared
  projection layer.
- `commands/automation.py` delegates inspect config rendering to the shared
  projection layer.

## Publish Contract

### Source Manifest Present

If the task directory contains `automation.toml`:

- load and validate it through `load_automation_manifest()`
- convert it through the shared projection layer into the snapshot manifest
  representation
- rewrite only the fields that must move into snapshot/runtime context, such as
  task and output paths
- preserve all supported fields semantically

### Source Manifest Absent

If the task directory does not contain `automation.toml`:

- generate the minimal default manifest
- mark the publish result as `manifest_source=generated_defaults`

### Invalid Source Manifest

If `automation.toml` exists but is invalid:

- fail publish
- do not silently regenerate from defaults

## Import Contract

`automation import` accepts manifest semantics only.

The import path must:

- load the manifest through `load_automation_manifest()`
- project it into `PersistedAutomationDefinition` through the shared projection
  layer
- preserve the entire supported field set in persisted live state

## Export Contract

`automation export` must:

- take the persisted live automation definition
- project it back into manifest semantics through the shared projection layer
- render TOML from those semantics

The resulting TOML does not need to match original source text, but
reloading it through `load_automation_manifest()` must produce supported-field
semantics equivalent to the persisted source definition.

## Inspect Contract

`browser-cli automation inspect <automation-id>` remains the live operational
view.

`browser-cli automation inspect <automation-id> --version N` must continue to
show:

- `snapshot_config` from the immutable snapshot manifest
- `live_config` from the current persisted automation definition
- `latest_run` as a separate operational section

This design adds a stronger rule:

- `snapshot_config` and `live_config` must be rendered from the same shared
  inspect-config projection shape

Allowed differences:

- path values may differ because one view is snapshot-scoped and the other is
  live-runtime-scoped
- operational metadata such as `enabled`, timestamps, and latest run remains
  live-only data

Disallowed differences:

- one view exposing a supported config field while the other omits it
- one view renaming or reshaping supported fields differently from the other

## File-Level Change Plan

### `src/browser_cli/automation/projections.py`

New shared projection helpers for:

- manifest to persisted definition
- persisted definition to manifest sections
- manifest to snapshot manifest sections with path remapping
- manifest/persisted definition to shared inspect config payloads

### `src/browser_cli/automation/models.py`

Keep dataclasses. Existing projection helpers either become thin wrappers or
move entirely to the new projection layer.

### `src/browser_cli/automation/publisher.py`

Replace local snapshot-manifest assembly with shared projection helpers.

### `src/browser_cli/automation/api/server.py`

Replace local import/export field projection with shared projection helpers.

### `src/browser_cli/commands/automation.py`

Replace separate live/snapshot inspect payload assembly with shared inspect
config projection helpers.

## Testing Strategy

The validation focus is semantic round-trip coverage, not raw text comparison.

Required regression coverage:

- source manifest -> persisted definition preserves supported fields
- persisted definition -> exported TOML -> reloaded manifest preserves
  supported fields semantically
- source manifest -> published snapshot manifest -> reloaded manifest preserves
  supported fields semantically after path remapping
- `inspect --version` renders `snapshot_config` and `live_config` with the same
  supported config field set

At minimum, tests must cover:

- `inputs`
- `schedule.timezone`
- schedule payload fields beyond `mode/timezone` where supported
- `outputs.result_json_path`
- `hooks.before_run`
- `hooks.after_success`
- `hooks.after_failure`
- `runtime.retry_attempts`
- `runtime.retry_backoff_seconds`
- `runtime.timeout_seconds`
- `runtime.log_level`

## Acceptance Criteria

This work is complete when all of the following are true:

1. Publishing a task with source `automation.toml` no longer drops supported
   manifest fields in the published snapshot.
2. Exported automation TOML can be reloaded without semantic loss of supported
   fields.
3. Import preserves the supported field set into persisted live automation
   state.
4. `inspect --version` continues to separate snapshot truth from live truth.
5. `snapshot_config` and `live_config` share one stable config-view field
   shape.
6. Path rewriting may occur, but no supported field changes meaning across
   round-trip paths.

## Risks And Mitigations

- Risk: moving projection logic can break existing payload shapes.
  Mitigation: keep the public inspect/live response structure intact and change
  only config payload assembly behind it.

- Risk: duplicated legacy helpers may continue drifting after the refactor.
  Mitigation: centralize supported-field projection in one new module and make
  other surfaces delegate to it.

- Risk: tests may accidentally assert exact text output instead of semantics.
  Mitigation: use `load_automation_manifest()` and structured payload
  comparisons as the primary assertions.

## Result

After this change, Browser CLI still has two truths:

- immutable published snapshot configuration
- current live persisted automation configuration

But both truths are interpreted through one shared manifest semantic contract.

That is the release-ready consistency bar for Browser CLI's automation
round-trip behavior.
