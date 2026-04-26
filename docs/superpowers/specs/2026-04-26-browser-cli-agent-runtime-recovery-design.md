# Browser CLI Agent Runtime Recovery Design

Date: 2026-04-26
Status: Drafted for review
Repo: `/home/hongv/workspace/browser-cli`

## Summary

Browser CLI needs a more agent-friendly runtime surface for daemon health,
workspace binding recovery, long command polling, and headless/container
diagnosis.

The current runtime already has most of the raw facts:

- `runtime-status` returns daemon-owned `presentation`
- `BrowserService.rebuild_workspace_binding()` can rebuild extension workspace
  state
- `BROWSER_CLI_EXTENSION_HOST` and `BROWSER_CLI_EXTENSION_PORT` already exist
- `doctor --json` already returns structured checks

The missing layer is a stable command contract that agents can inspect, repair,
and poll without scraping human text or relying on shell process state.

This design keeps daemon-owned runtime state as the source of truth. CLI
commands project that state into stable JSON and route recovery actions back
through daemon handlers.

## Goals

- Add `browser-cli status --json` with a stable, documented schema.
- Expose non-interactive workspace recovery through:
  - `browser-cli workspace rebuild --json`
  - `browser-cli recover --json`
- Add safe command-start preflight that can rebuild stale or absent extension
  workspace binding.
- Preserve human-readable stderr for normal commands while returning structured
  JSON errors for JSON-mode commands.
- Add `read --json` for synchronous reads and `read --async --json` for
  daemon-side polling.
- Add a lightweight in-memory daemon run registry for async read commands.
- Improve `doctor --json` for container, headless, Chrome discovery, and
  extension listener port diagnosis.
- Make extension listener host and port observable in status and run-info.

## Non-Goals

- No public `browser-cli explore` command.
- No second browser runtime.
- No persisted async run history in this design. Async command runs are daemon
  process memory only.
- No broad async support for every daemon-backed action in the first
  implementation. First version supports `read --async --json`.
- No silent extension listener port reassignment. If the configured port cannot
  bind, Browser CLI reports the failure and suggests an env override.
- No CLI-side reimplementation of runtime health classification.

## Options Considered

### 1. Layer stable agent surfaces on daemon-owned runtime truth

`runtime-status` and daemon `presentation` remain the truth. `status --json`
is a stable projection. Recovery commands call daemon actions. Preflight lives
in `BrowserService.begin_command()`. Async read runs live in a daemon registry.

Advantages:

- matches the existing daemon/runtime boundaries
- avoids a second classifier in the CLI
- lets status, popup, commands, and recovery share one runtime model
- can be implemented incrementally

Tradeoff:

- `recover --json` becomes a small orchestration command and must avoid
  duplicating too much of `reload`
- preflight metadata needs careful propagation through success and error
  responses

Chosen direction.

### 2. Add a separate recovery service abstraction

Create a new recovery or runtime-health service used by CLI and daemon code.

Advantages:

- may become cleaner if recovery logic grows much larger
- centralizes policy in one named module

Tradeoff:

- risks premature abstraction over existing `runtime_presentation.py`
- turns this feature into a broader refactor

Deferred.

### 3. Build recovery mostly as CLI wrappers

Let CLI combine `runtime-status`, `reload`, and extension popup endpoints.

Advantages:

- smaller short-term daemon changes

Tradeoff:

- duplicates runtime classification in CLI
- weakens the daemon-owned presentation contract
- makes command-start preflight difficult to implement correctly

Rejected.

## Chosen Direction

Use option 1: add stable agent-facing command surfaces while preserving daemon
runtime state as the single source of truth.

The implementation should proceed in phases:

1. `status --json`
2. daemon action `workspace-rebuild-binding`
3. CLI `workspace rebuild --json`
4. CLI `recover --json`
5. safe `begin_command()` preflight
6. async read run registry and `run-*` commands
7. doctor/headless/container/port diagnosis

The phases are ordered so the recovery foundation lands before async polling
and environment diagnostics.

## Stable Status JSON

`browser-cli status --json` returns a stable projection, not the complete
internal `StatusReport`.

Shape:

```json
{
  "ok": true,
  "data": {
    "status": "healthy",
    "daemon": {
      "state": "running",
      "pid": 4083,
      "socket_reachable": true
    },
    "backend": {
      "active_driver": "extension",
      "extension_connected": true,
      "extension_capability_complete": true,
      "extension_listener": {
        "host": "127.0.0.1",
        "port": 19825,
        "ws_url": "ws://127.0.0.1:19825/ext"
      }
    },
    "browser": {
      "started": true,
      "workspace_binding": "tracked"
    },
    "recovery": {
      "recommended_action": "none",
      "available_actions": ["refresh-status"]
    }
  },
  "meta": {
    "action": "status"
  }
}
```

Allowed `data.status` values:

- `healthy`
- `degraded`
- `recovering`
- `broken`
- `stopped`

Allowed `browser.workspace_binding` values:

- `tracked`
- `stale`
- `absent`
- `unknown`

Allowed `recovery.recommended_action` values:

- `none`
- `reload`
- `reconnect-extension`
- `rebuild-workspace-binding`

The status command should derive runtime health from daemon
`presentation.overall_state` when a compatible daemon is reachable. When no
live daemon payload is available, it uses existing daemon reachability
classification.

Recommendation priority:

1. stale, incompatible, or broken daemon state -> `reload`
2. extension mode with connected, capability-complete extension and
   `workspace_binding` in `stale|absent` -> `rebuild-workspace-binding`
3. extension missing or capability-incomplete -> `reconnect-extension`
4. otherwise -> `none`

`StatusReport` remains the richer internal object for human text rendering.
Tests should lock a dedicated serializer such as
`status_report_to_json_data(report)` so the stable schema is not accidentally
tied to text output fields.

## Workspace Recovery Commands

### `browser-cli workspace rebuild --json`

This command is the precise non-interactive binding repair action.

Behavior:

- starts the daemon if needed
- collects stable before status
- sends daemon action `workspace-rebuild-binding`
- collects stable after status
- returns action result and `recovered`

Success shape:

```json
{
  "ok": true,
  "data": {
    "before_status": {},
    "action_taken": "rebuild-workspace-binding",
    "after_status": {},
    "recovered": true
  },
  "meta": {
    "action": "workspace-rebuild"
  }
}
```

If extension is unavailable, the command returns a JSON failure with
`EXTENSION_UNAVAILABLE` and `next_action`.

If extension is connected but capability-incomplete, it returns
`EXTENSION_CAPABILITY_INCOMPLETE`.

This explicit command does not fallback to Playwright. It either rebuilds the
extension workspace binding or reports why it cannot.

### `browser-cli recover --json`

This command is the broader agent recovery entrypoint.

Behavior:

- starts the daemon if needed
- collects stable before status
- if daemon state is stale, incompatible, broken, or extension unavailable,
  attempts `browser-cli reload` semantics
- re-checks status
- if extension is connected, capability-complete, and workspace binding is
  `absent|stale`, calls `workspace-rebuild-binding`
- returns before status, action taken, after status, and recovered flag

Allowed `action_taken` values:

- `none`
- `reload`
- `rebuild-workspace-binding`
- `reload+rebuild-workspace-binding`

`recover --json` may be more aggressive than `workspace rebuild --json`.
It is the default agent action when status says recovery is needed but the
specific root cause may require a daemon restart first.

## Command Start Preflight

`BrowserService.begin_command()` gains a narrow automatic recovery preflight.

It attempts workspace rebuild only when all conditions are true:

- active driver is `extension`
- extension is connected
- extension has all required capabilities
- `command_depth == 0`
- workspace binding is `absent` or `stale`
- no tabs are busy

If rebuild succeeds:

- original command continues
- response meta includes preflight success
- existing `driver_reason: workspace-binding-rebuilt` and `state_reset: true`
  continue to report the reset

If rebuild fails but extension is still connected and capability-complete:

- original command continues on extension
- response meta includes structured preflight failure

If rebuild fails and extension is disconnected or capability-incomplete:

- existing safe fallback behavior applies: switch to Playwright and execute the
  command there
- response meta reports both preflight failure and driver transition reason

The final behavior is intentionally not a hard block. The selected policy is:
preflight failure must not be silent, but it should not prevent a command from
running when Browser CLI has a safe execution path.

Example `meta.preflight`:

```json
{
  "attempted": true,
  "action": "rebuild-workspace-binding",
  "ok": false,
  "error_code": "WORKSPACE_BINDING_LOST",
  "message": "Workspace binding could not be rebuilt.",
  "next_action": "browser-cli recover --json"
}
```

If no preflight was needed, omit `meta.preflight` to avoid noisy command
payloads.

## Structured Errors

Add or standardize these error codes:

- `WORKSPACE_BINDING_LOST`
- `EXTENSION_UNAVAILABLE`
- `EXTENSION_CAPABILITY_INCOMPLETE`
- `EXTENSION_PORT_IN_USE`
- `CHROME_EXECUTABLE_NOT_FOUND`
- `HEADLESS_RUNTIME_UNAVAILABLE`

Daemon responses keep the existing shape:

```json
{
  "ok": false,
  "data": {},
  "meta": {
    "action": "workspace-rebuild",
    "agent_id": "public",
    "next_action": "browser-cli recover --json"
  },
  "error_code": "WORKSPACE_BINDING_LOST",
  "error_message": "Workspace binding was lost."
}
```

JSON-mode CLI commands return a simpler command-line error payload:

```json
{
  "ok": false,
  "error_code": "WORKSPACE_BINDING_LOST",
  "message": "Workspace binding was lost.",
  "next_action": "browser-cli workspace rebuild --json"
}
```

Human-mode commands continue to write human-readable stderr with optional
`Next:` guidance.

The first implementation should apply JSON error output to:

- `status --json`
- `read --json`
- `doctor --json`
- `workspace rebuild --json`
- `recover --json`
- `run-status --json`
- future JSON-only `run-*` surfaces

It should not globally change every existing CLI command's error behavior.

## `read --json` And Async Read

`read` remains content-first unless `--json` is present.

Synchronous command forms:

- `browser-cli read <url> --json`
- `browser-cli read <url> --snapshot --json`

Synchronous success shape:

```json
{
  "ok": true,
  "data": {
    "body": "...",
    "output_mode": "snapshot",
    "used_fallback_profile": false,
    "fallback_profile_dir": null,
    "fallback_reason": null
  },
  "meta": {
    "action": "read"
  }
}
```

Without `--json`, `read` keeps returning only the rendered HTML or snapshot
body on stdout, with fallback profile info on stderr.

Async first version supports only the `read` command, with the same read
options as synchronous mode:

```bash
browser-cli read <url> [--snapshot] [--scroll-bottom] --async --json
```

`read --async --json` sends daemon action `run-start-read`. The daemon creates
an in-memory run record and returns immediately.

Start response:

```json
{
  "ok": true,
  "data": {
    "run_id": "run_000001",
    "status": "queued",
    "command": "read",
    "poll": "browser-cli run-status run_000001 --json"
  },
  "meta": {
    "action": "read-async"
  }
}
```

## Async Run Registry

The daemon owns a lightweight command-run registry for async read commands.

Run states:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancel_requested`
- `canceled`
- `not_found`

Commands:

- `browser-cli run-status <run_id> --json`
- `browser-cli run-logs <run_id> --tail 200`
- `browser-cli run-cancel <run_id>`

`run-status --json` returns run metadata, current status, result if complete,
and structured error if failed.

`run-logs` returns a bounded event log, not a full copy of captured page output.
Events include items such as `queued`, `started`, `completed`, `failed`, and
`canceled`.

`run-cancel` cancels the daemon task. If the underlying browser operation cannot
stop immediately, the registry records `cancel_requested` until the task
settles as `canceled` or `failed`.

The registry is process memory only. If the daemon restarts, previous run ids
are not recoverable. `run-status` should return `not_found` with a clear
message in that case.

The first implementation should design the registry so other daemon-backed
commands can be added later, but only `read` needs to use it now.

## Headless, Container, And Port Diagnostics

`BROWSER_CLI_EXTENSION_HOST` and `BROWSER_CLI_EXTENSION_PORT` are already stable
configuration. This design makes them visible and diagnosable.

Daemon run-info should include:

```json
{
  "extension_host": "127.0.0.1",
  "extension_port": 19825,
  "extension_ws_url": "ws://127.0.0.1:19825/ext",
  "headless": true
}
```

`status --json` should expose the extension listener endpoint at
`data.backend.extension_listener`.

`doctor --json` gains an `environment` section:

```json
{
  "environment": {
    "in_container": true,
    "container_markers": ["/.dockerenv"],
    "headless_env": "1",
    "headless_effective": true,
    "extension_host": "127.0.0.1",
    "extension_port": 19825
  }
}
```

Doctor checks should include or enhance:

- `chrome_candidates`: candidate Chrome and Chromium paths and whether each
  exists
- `chrome`: return `CHROME_EXECUTABLE_NOT_FOUND` when no supported executable
  is found
- `headless`: report whether `BROWSER_CLI_HEADLESS=1` is effective; warn in a
  container when headless is not enabled
- `container`: report lightweight container detection markers
- `extension_port`: attempt to bind the configured extension host and port

Port ownership should be best-effort. If `lsof` or `ss` is available, doctor
may include a process summary. If not, it still reports bind failure and
suggests `BROWSER_CLI_EXTENSION_PORT=<free-port>` or stopping the occupying
process.

`ExtensionHub.ensure_started()` should wrap listener bind failures as
`EXTENSION_PORT_IN_USE` when the failure is address-in-use. Daemon startup
should fail explicitly rather than silently selecting another port, because the
browser extension needs a predictable endpoint.

## Testing

Add unit tests for:

- parser exposes `status --json`, `workspace rebuild --json`, `recover --json`,
  `read --json`, `read --async --json`, and `run-*` commands
- `status_report_to_json_data()` returns the stable status schema
- status recommendation priority for stopped, broken, extension unavailable,
  stale workspace binding, and healthy states
- daemon action `workspace-rebuild-binding` success and extension unavailable
  failures
- `recover --json` action sequencing for reload-only, rebuild-only, combined,
  and no-op cases
- preflight success, preflight recoverable failure, and preflight failure that
  falls back to Playwright
- JSON-mode errors include `error_code`, `message`, and `next_action`
- sync `read --json` wraps body and fallback metadata without changing non-json
  output
- async read start, status, logs, cancel, completion, failure, and daemon
  restart/not-found behavior
- doctor environment and extension port diagnostics

Run the normal validation sequence after implementation:

```bash
scripts/lint.sh
scripts/test.sh
scripts/guard.sh
```

or:

```bash
scripts/check.sh
```

## AGENTS.md Updates

This feature changes public CLI surfaces and recurring debugging paths, so the
implementation should update `AGENTS.md` when code lands.

Durable additions should include:

- `status --json` is the stable agent status surface
- `workspace rebuild --json` is the precise workspace binding repair command
- `recover --json` is the broader recovery command
- async read runs are daemon-memory only in the first version
- extension listener host and port are configured by
  `BROWSER_CLI_EXTENSION_HOST` and `BROWSER_CLI_EXTENSION_PORT`
- doctor owns container/headless/extension-port diagnostics
