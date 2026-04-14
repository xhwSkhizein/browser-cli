# Browser CLI Release Readiness Design

Date: 2026-04-14
Status: Drafted for review
Repo: `browser-cli`

## Summary

This design closes a set of release-blocking consistency gaps across the
automation publish chain, automation manifest round-tripping, automation run
timeouts, and one-shot read fallback reporting.

The unifying rule is:

- a published automation version is defined by the immutable snapshot under
  `~/.browser-cli/automations/<automation-id>/versions/<version>/`
- that snapshot truth includes `task.py`, `task.meta.json`, and the
  version-specific `automation.toml`
- current automation-service state is a separate live view and must not be
  confused with historical snapshot truth

This design does not introduce a new product surface. It tightens the existing
contracts so the first public release behaves consistently with the current
documentation and user model.

## Problem Statement

The repository is close to release quality, but several mismatches remain:

- `automation publish` snapshots task code but currently regenerates automation
  configuration from defaults, which discards reviewed source configuration
- automation manifest fields are not modeled consistently across load, import,
  export, inspect, and persistence paths
- `runtime.timeout_seconds` exists as public configuration but is not enforced
  by automation execution
- `inspect --version` does not cleanly distinguish immutable snapshot config
  from current live automation state
- one-shot `read` fallback profile reporting was preserved in lower layers but
  was lost on the daemon-backed read path

These failures all have the same user-visible effect: Browser CLI exposes a
configuration surface that appears stable, but some paths silently change or
discard information.

## Goals

- Preserve reviewed `automation.toml` configuration when publishing a task.
- Keep published automation versions immutable and self-describing.
- Make snapshot truth and live service state clearly separable in inspect
  output.
- Make supported automation manifest fields round-trip without silent loss
  across import, export, publish, and inspect.
- Enforce `runtime.timeout_seconds` as a real automation-service behavior.
- Keep timeout failure semantics explicit: run-level total timeout, no automatic
  retry on timeout.
- Restore fallback profile reporting for `browser-cli read`.

## Non-Goals

- No change to `task run` semantics. `task.meta.json` remains a reference and
  sidecar artifact, not a runtime requirement for execution.
- No expansion of daemon-wide response metadata for all commands.
- No automation timeout support for local `browser-cli task run`.
- No broader daemon/runtime architecture changes beyond the targeted fixes.
- No new public `automation` subcommands.

## Chosen Direction

Browser CLI should treat the snapshot manifest as the configuration truth for a
published version, while treating the automation-service database as the truth
for current live state.

That produces five explicit rules:

1. `automation publish` snapshots task code and configuration together.
2. If source `automation.toml` exists, publish uses it as the configuration
   truth.
3. If source `automation.toml` does not exist, publish may still proceed, but
   the generated defaults must be explicit in the published metadata.
4. `inspect --version N` shows the immutable snapshot configuration for version
   `N`, while current live configuration is shown separately.
5. `runtime.timeout_seconds` is a run-level total timeout budget enforced by
   the automation service, not a dead configuration field.

## Options Considered

### 1. Minimal Bug Fixes Only

Patch each reported bug independently without introducing a tighter release
model.

Advantages:

- smallest patch set
- lowest immediate implementation risk

Disadvantages:

- leaves the publish/import/export/inspect flow conceptually fragmented
- makes future regressions more likely because there is no single truth model

Rejected.

### 2. Snapshot-Truth Consistency Repair

Define a single release model around immutable snapshot manifests, align
publish/import/export/inspect to that model, and enforce timeout/fallback
behavior where the public contract already promises it.

Advantages:

- matches the existing task/automation design
- fixes the current release blockers without widening scope unnecessarily
- gives inspect and publish a clear mental model

Disadvantages:

- requires coordinated updates across several automation modules
- increases the amount of contract-focused testing that must be updated

Chosen direction.

### 3. Broader Runtime Contract Unification

Use this work to redesign more of the daemon and automation metadata model.

Advantages:

- could simplify future work further

Disadvantages:

- too large for the current pre-release window
- risks mixing release fixes with unrelated contract redesign

Rejected.

## Publish Contract

### Source Inputs

`browser-cli automation publish <task-dir>` consumes:

- required: `task.py`
- required: `task.meta.json`
- optional: `automation.toml`

### Publish Behavior

Publish must validate `task.py` and `task.meta.json` first.

Then publish determines the manifest source:

- if `automation.toml` exists in the source task directory, load and validate it
  and use it as the release configuration truth
- if `automation.toml` does not exist, generate the minimal default manifest and
  mark the published result as `manifest_source=generated_defaults`
- if `automation.toml` exists but is invalid, fail publish; do not silently fall
  back to defaults

The publish output snapshot must contain:

- `task.py`
- `task.meta.json`
- the final resolved `automation.toml`
- `publish.json`

The canonical snapshot location remains:

```text
~/.browser-cli/automations/<automation-id>/versions/<version>/
```

### Publish Result Metadata

Publish output should explicitly include:

- `manifest_source`
  - `task_dir`
  - `generated_defaults`
- snapshot path
- version
- automation id
- a concise summary of the resolved published configuration

This is an additive contract improvement. It does not change the public command
name or the broader task/automation model.

## Manifest Modeling And Round-Trip Rules

### Supported Fields

The automation manifest loader, persistence conversion, export path, and inspect
path must agree on the same supported field set.

At minimum, the currently supported fields that must no longer be silently lost
are:

- `inputs`
- schedule fields including `mode` and `timezone`
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

### Round-Trip Expectations

The round-trip requirements are:

- `automation import` must preserve all supported fields into persisted
  automation state
- `automation export` must faithfully render supported persisted fields back to
  `automation.toml`
- `automation publish` must preserve supported source manifest fields when
  producing the versioned snapshot manifest
- snapshot inspect must reflect the supported fields stored in the versioned
  snapshot manifest

Silent field loss is not acceptable for supported fields.

Unknown-field preservation is not a goal in this design. The contract is based
on complete handling of the supported schema, not lossless passthrough of
arbitrary TOML.

## Inspect Contract

### Live Inspect

`browser-cli automation inspect <automation-id>` without `--version` should show
the current persisted automation definition plus the latest run summary.

This is the live operational view.

### Versioned Inspect

`browser-cli automation inspect <automation-id> --version N` should show two
separate configuration views:

- `snapshot_config`
  - loaded from
    `~/.browser-cli/automations/<automation-id>/versions/<N>/automation.toml`
  - represents the immutable configuration that was published for that version
- `live_config`
  - loaded from the current persisted automation definition in the automation
    service
  - represents the current service configuration, which may reflect a newer
    publish or an import/update path

`latest_run` remains a separate operational section.

This separation is required so users can answer three different questions
without ambiguity:

- what was published in version `N`
- what is currently configured in the automation service
- what happened in the most recent run

### Error Handling

If the requested snapshot version exists but its manifest cannot be loaded,
inspect must not silently replace the broken snapshot view with live config.
Instead it should expose a dedicated error field such as
`snapshot_config_error`.

## Timeout Contract

### Semantics

`runtime.timeout_seconds` must mean the total wall-clock time budget for one
automation run while it occupies the executor.

This is a run-level timeout, not a task-function-only timeout.

The timeout budget covers the main run path, including:

- daemon readiness checks performed as part of run execution
- `before_run` hooks
- `task.py` execution
- main result handling before final success/failure state is recorded

### Failure Semantics

If the timeout budget is exceeded:

- the run is marked `failed`
- the run receives a dedicated timeout error code
- timeout does not participate in automatic retry, even if
  `retry_attempts > 0`

This makes timeout behavior explicit and avoids turning “the run exceeded its
budget” into a silent retry loop.

### Failure Hooks

`after_failure` hooks may still run after timeout, but they must not be allowed
to hang indefinitely. They should run under a separate bounded timeout budget.

The design does not require one specific implementation strategy for that hook
timeout, but it does require bounded behavior.

### Timeout Scope Boundary

Timeout remains an automation-service concern only.

It should not be pushed into:

- `browser-cli task run`
- `browser_cli.task_runtime`
- general daemon command handling

This keeps local task execution behavior stable and prevents automation-service
policy from leaking into the reusable task runtime.

## Read Fallback Reporting

The fix scope is intentionally narrow.

Fallback profile reporting should be restored only for the one-shot read path:

- daemon `read-page`
- task runtime `read`
- CLI `browser-cli read`

The daemon-backed read response must again include the fallback profile metadata
already used by the user-facing read command:

- `used_fallback_profile`
- `fallback_profile_dir`
- `fallback_reason`

The CLI should continue printing the user-facing stderr notice only on the read
surface.

This design explicitly does not promote fallback/profile details into the
general response contract of every daemon-backed action.

## Module Responsibilities

### `browser_cli.automation.loader`

- fully parse the supported manifest schema
- stop dropping supported runtime fields such as
  `retry_backoff_seconds`

### `browser_cli.automation.models`

- model the same supported runtime fields that loader/import/export/persistence
  support
- keep manifest-to-persisted conversion aligned with the supported schema

### `browser_cli.automation.publisher`

- determine manifest source during publish
- load source `automation.toml` when present
- generate defaults only when the source manifest is absent
- write the final resolved manifest into the snapshot directory
- return `manifest_source` metadata

### `browser_cli.commands.automation`

- present publish results clearly
- keep import/export/inspect response shapes aligned with the supported field
  set
- expose snapshot/live separation in inspect output

### `browser_cli.automation.api.server`

- accept and return the full supported field set for persisted automations
- avoid silently defaulting supported fields when they were supplied upstream

### `browser_cli.automation.service.runtime`

- enforce run-level timeout semantics
- enforce “timeout does not auto-retry”
- emit explicit timeout failure information in run events/status

### `browser_cli.daemon.browser_service`

- restore fallback metadata on `read_page`

## Testing Requirements

The release fix is not complete without contract-focused tests.

At minimum, tests should cover:

- publish preserves source `automation.toml` fields into the snapshot manifest
- publish without source `automation.toml` produces defaults and marks
  `manifest_source=generated_defaults`
- import/export preserve the supported manifest fields
- inspect with `--version` returns separate snapshot and live config views
- timeout fails a run when the total wall-clock budget is exceeded
- timeout failure does not schedule automatic retry
- read fallback metadata reaches `browser-cli read` again

The full repository validation bar remains:

- `scripts/lint.sh`
- `scripts/test.sh`
- `scripts/guard.sh`

or equivalently:

- `scripts/check.sh`

## Documentation Requirements

The documentation updates in this design are part of the implementation scope,
not follow-up polish.

At minimum, docs should make the following durable statements explicit:

- published automation versions live under
  `~/.browser-cli/automations/...`
- `automation publish` snapshots configuration from source
  `automation.toml` when present
- publish may use generated defaults only when source `automation.toml` is
  absent, and this is made explicit
- `inspect --version` shows snapshot config separately from live config
- `runtime.timeout_seconds` is a run-level total timeout

`AGENTS.md` should also be updated if any navigation or debugging guidance needs
to reflect the tightened snapshot/live truth rules.

## Expected Outcome

After this design is implemented:

- publishing a task no longer discards reviewed automation configuration
- supported manifest fields stop drifting across publish/import/export/inspect
- users can inspect historical snapshot truth and current live state separately
- automation timeout becomes a real supported behavior rather than a dead
  setting
- `browser-cli read` again explains when fallback profile mode was used

That is the minimum release-ready consistency bar for Browser CLI’s first public
version.
