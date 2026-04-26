# Browser CLI Agent Runtime Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add stable agent-facing status, recovery, JSON errors, async read polling, and headless/container diagnostics for Browser CLI's daemon runtime.

**Architecture:** Keep daemon `runtime-status` and `presentation` as the runtime truth. CLI commands project stable JSON and call daemon actions for repair; daemon `BrowserService` owns preflight recovery and in-memory async read runs. Doctor diagnostics stay read-only and report environment facts without changing runtime configuration.

**Tech Stack:** Python 3.10, argparse, asyncio, pytest, Browser CLI daemon socket protocol, Playwright/extension drivers, Markdown docs

---

## File Structure

- Modify: `src/browser_cli/error_codes.py`
  - Add stable recovery and environment error code constants.
- Modify: `src/browser_cli/errors.py`
  - Add typed errors for workspace binding, extension availability, Chrome executable, headless runtime, and extension port binding.
- Modify: `src/browser_cli/cli/error_hints.py`
  - Add `next_action` hints for new error codes.
- Modify: `src/browser_cli/outputs/json.py`
  - Add a small JSON error renderer used by JSON-mode CLI commands.
- Modify: `src/browser_cli/cli/main.py`
  - Render `BrowserCliError` as JSON for commands invoked with `--json`.
- Modify: `src/browser_cli/commands/status.py`
  - Add `status_report_to_json_data(...)`, stable recommendation logic, and `run_status_command(... --json)`.
- Modify: `src/browser_cli/cli/main.py`
  - Add parser flags and new command families: `status --json`, `workspace rebuild --json`, `recover --json`, `read --json`, `read --async`, and `run-*`.
- Create: `src/browser_cli/commands/recovery.py`
  - Own CLI orchestration for `workspace rebuild --json` and `recover --json`.
- Modify: `src/browser_cli/daemon/app.py`
  - Add daemon handlers for `workspace-rebuild-binding`, async run actions, and preflight meta propagation.
- Modify: `src/browser_cli/daemon/browser_service.py`
  - Add safe preflight workspace rebuild and structured preflight metadata.
- Create: `src/browser_cli/daemon/run_registry.py`
  - Own process-memory async run records, event logs, task cancellation, and async read execution.
- Modify: `src/browser_cli/daemon/state.py`
  - Add one run registry instance to daemon state.
- Modify: `src/browser_cli/commands/read.py`
  - Add sync `--json` output and async read start path.
- Modify: `src/browser_cli/task_runtime/read.py`
  - Keep sync read contract stable; no async registry state belongs in this module.
- Modify: `src/browser_cli/daemon/server.py`
  - Write extension host/port/ws URL and effective headless mode to run-info.
- Modify: `src/browser_cli/extension/session.py`
  - Wrap extension listener bind failures with `EXTENSION_PORT_IN_USE`.
- Modify: `src/browser_cli/commands/doctor.py`
  - Add environment, container, headless, Chrome candidate, and extension port diagnostics.
- Modify: `AGENTS.md`
  - Add durable navigation and debugging notes for the new surfaces.
- Tests:
  - Modify: `tests/unit/test_cli.py`
  - Modify: `tests/unit/test_lifecycle_commands.py`
  - Modify: `tests/unit/test_runtime_presentation.py`
  - Modify: `tests/unit/test_daemon_browser_service.py`
  - Modify: `tests/unit/test_doctor_command.py`
  - Modify: `tests/unit/test_error_hints.py`
  - Create: `tests/unit/test_recovery_commands.py`
  - Create: `tests/unit/test_daemon_run_registry.py`

## Implementation Tasks

### Task 1: Stable `status --json`

**Files:**
- Modify: `src/browser_cli/commands/status.py`
- Modify: `src/browser_cli/cli/main.py`
- Modify: `tests/unit/test_lifecycle_commands.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Write failing CLI parser and status serializer tests**

Add to `tests/unit/test_cli.py`:

```python
def test_status_help_mentions_json(capsys) -> None:
    exit_code = main(["status", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--json" in captured.out
    assert "runtime state" in captured.out
```

Add to `tests/unit/test_lifecycle_commands.py`:

```python
import json


def test_status_json_returns_stable_agent_schema(tmp_path: Path) -> None:
    run_info = {
        "pid": 4083,
        "package_version": __version__,
        "runtime_version": "2026-04-10-dual-driver-extension-v1",
    }
    runtime_status = {
        "browser_started": True,
        "active_driver": "extension",
        "profile_source": "extension",
        "profile_dir": None,
        "profile_directory": None,
        "extension": {
            "connected": True,
            "capability_complete": True,
            "missing_capabilities": [],
        },
        "pending_rebind": None,
        "workspace_window_state": {
            "window_id": 91,
            "tab_count": 1,
            "managed_tab_count": 1,
            "binding_state": "stale",
        },
        "tabs": {"count": 1, "busy_count": 0, "records": [], "active_by_agent": {}},
        "presentation": {
            "overall_state": "degraded",
            "summary_reason": "Workspace binding is stale while extension mode is active.",
            "available_actions": [
                "refresh-status",
                "reconnect-extension",
                "rebuild-workspace-binding",
            ],
            "workspace_state": {"binding_state": "stale", "busy_tab_count": 0},
        },
    }
    paths = _fake_paths(tmp_path)
    with (
        patch("browser_cli.commands.status.get_app_paths", return_value=paths),
        patch("browser_cli.commands.status.read_run_info", return_value=run_info),
        patch("browser_cli.commands.status.probe_socket", return_value=True),
        patch(
            "browser_cli.commands.status.send_command",
            return_value={"ok": True, "data": runtime_status},
        ),
    ):
        payload = json.loads(run_status_command(Namespace(json=True)))

    assert payload == {
        "ok": True,
        "data": {
            "status": "degraded",
            "daemon": {"state": "running", "pid": 4083, "socket_reachable": True},
            "backend": {
                "active_driver": "extension",
                "extension_connected": True,
                "extension_capability_complete": True,
                "extension_listener": {
                    "host": "127.0.0.1",
                    "port": 19825,
                    "ws_url": "ws://127.0.0.1:19825/ext",
                },
            },
            "browser": {"started": True, "workspace_binding": "stale"},
            "recovery": {
                "recommended_action": "rebuild-workspace-binding",
                "available_actions": [
                    "refresh-status",
                    "reconnect-extension",
                    "rebuild-workspace-binding",
                ],
            },
        },
        "meta": {"action": "status"},
    }
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
uv run pytest tests/unit/test_cli.py::test_status_help_mentions_json tests/unit/test_lifecycle_commands.py::test_status_json_returns_stable_agent_schema -v
```

Expected: parser test fails because `--json` is missing or serializer test fails because `run_status_command` renders text.

- [ ] **Step 3: Add `--json` parser support**

In `src/browser_cli/cli/main.py`, update the status parser block:

```python
    status_parser = subparsers.add_parser(
        "status",
        help="Show daemon, backend, and workspace runtime status.",
        description="Inspect Browser CLI runtime state and print operational guidance.",
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Return stable machine-readable runtime status.",
    )
    status_parser.set_defaults(handler=run_status_command)
```

- [ ] **Step 4: Add stable status JSON projection**

In `src/browser_cli/commands/status.py`, import `render_json_payload`:

```python
from browser_cli.outputs.json import render_json_payload
```

Replace `run_status_command` with:

```python
def run_status_command(args: Namespace) -> str:
    report = collect_status_report()
    if getattr(args, "json", False):
        return render_json_payload(
            {"ok": True, "data": status_report_to_json_data(report), "meta": {"action": "status"}}
        )
    return render_status_report(report)
```

Add these helpers near `render_status_report`:

```python
def status_report_to_json_data(report: StatusReport) -> dict[str, Any]:
    app_paths = get_app_paths()
    workspace_binding = _workspace_binding_state(report)
    available_actions = list(report.presentation.get("available_actions") or [])
    return {
        "status": report.overall_status,
        "daemon": {
            "state": report.daemon["state"],
            "pid": report.daemon["pid"],
            "socket_reachable": bool(report.daemon["socket_reachable"]),
        },
        "backend": {
            "active_driver": report.backend["active_driver"],
            "extension_connected": bool(report.backend["extension_connected"]),
            "extension_capability_complete": bool(
                report.backend["extension_capability_complete"]
            ),
            "extension_listener": {
                "host": app_paths.extension_host,
                "port": app_paths.extension_port,
                "ws_url": app_paths.extension_ws_url,
            },
        },
        "browser": {
            "started": bool(report.backend["browser_started"]),
            "workspace_binding": workspace_binding,
        },
        "recovery": {
            "recommended_action": _recommended_action(
                report=report,
                workspace_binding=workspace_binding,
                available_actions=available_actions,
            ),
            "available_actions": available_actions or ["refresh-status"],
        },
    }


def _workspace_binding_state(report: StatusReport) -> str:
    presentation_workspace = dict(report.presentation.get("workspace_state") or {})
    binding = str(presentation_workspace.get("binding_state") or "").strip()
    if binding in {"tracked", "stale", "absent"}:
        return binding
    return "unknown"


def _recommended_action(
    *,
    report: StatusReport,
    workspace_binding: str,
    available_actions: list[str],
) -> str:
    if report.daemon_state in {"stale", "incompatible"} or report.overall_status == "broken":
        return "reload"
    if (
        report.backend["active_driver"] == "extension"
        and report.backend["extension_connected"]
        and report.backend["extension_capability_complete"]
        and workspace_binding in {"stale", "absent"}
        and "rebuild-workspace-binding" in available_actions
    ):
        return "rebuild-workspace-binding"
    if (
        report.backend["active_driver"] == "extension"
        and (
            not report.backend["extension_connected"]
            or not report.backend["extension_capability_complete"]
        )
    ):
        return "reconnect-extension"
    return "none"
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/unit/test_cli.py::test_status_help_mentions_json tests/unit/test_lifecycle_commands.py::test_status_json_returns_stable_agent_schema -v
```

Expected: PASS.

- [ ] **Step 6: Run lifecycle status tests**

Run:

```bash
uv run pytest tests/unit/test_lifecycle_commands.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/browser_cli/cli/main.py src/browser_cli/commands/status.py tests/unit/test_cli.py tests/unit/test_lifecycle_commands.py
git commit -m "feat: add stable status json"
```

### Task 2: Structured Recovery Error Codes And JSON Error Rendering

**Files:**
- Modify: `src/browser_cli/error_codes.py`
- Modify: `src/browser_cli/errors.py`
- Modify: `src/browser_cli/cli/error_hints.py`
- Modify: `src/browser_cli/outputs/json.py`
- Modify: `src/browser_cli/cli/main.py`
- Modify: `tests/unit/test_error_hints.py`
- Modify: `tests/unit/test_cli.py`
- Create: `tests/unit/test_json_errors.py`

- [ ] **Step 1: Write failing error code and JSON renderer tests**

Create `tests/unit/test_json_errors.py`:

```python
from __future__ import annotations

import json

from browser_cli import error_codes
from browser_cli.errors import WorkspaceBindingLostError
from browser_cli.outputs.json import render_json_error


def test_render_json_error_uses_next_action() -> None:
    payload = json.loads(
        render_json_error(
            WorkspaceBindingLostError("Workspace binding was lost."),
            next_action="browser-cli workspace rebuild --json",
        )
    )
    assert payload == {
        "ok": False,
        "error_code": "WORKSPACE_BINDING_LOST",
        "message": "Workspace binding was lost.",
        "next_action": "browser-cli workspace rebuild --json",
    }


def test_new_recovery_error_codes_are_stable() -> None:
    assert error_codes.WORKSPACE_BINDING_LOST == "WORKSPACE_BINDING_LOST"
    assert error_codes.EXTENSION_PORT_IN_USE == "EXTENSION_PORT_IN_USE"
    assert error_codes.CHROME_EXECUTABLE_NOT_FOUND == "CHROME_EXECUTABLE_NOT_FOUND"
    assert error_codes.HEADLESS_RUNTIME_UNAVAILABLE == "HEADLESS_RUNTIME_UNAVAILABLE"
```

Add to `tests/unit/test_error_hints.py`:

```python
from browser_cli.errors import (
    ChromeExecutableNotFoundError,
    ExtensionPortInUseError,
    WorkspaceBindingLostError,
)


def test_recovery_error_hints() -> None:
    assert (
        next_hint_for_error(WorkspaceBindingLostError("lost"))
        == "run browser-cli workspace rebuild --json"
    )
    assert (
        next_hint_for_error(ExtensionPortInUseError("port busy"))
        == "set BROWSER_CLI_EXTENSION_PORT to a free port or stop the process using it"
    )
    assert (
        next_hint_for_error(ChromeExecutableNotFoundError("missing"))
        == "install stable Google Chrome and re-run browser-cli doctor --json"
    )
```

Add to `tests/unit/test_cli.py`:

```python
def test_json_mode_error_renders_json_to_stdout(capsys) -> None:
    with patch(
        "browser_cli.cli.main.run_doctor_command",
        side_effect=ChromeExecutableNotFoundError("Chrome missing"),
    ):
        exit_code = main(["doctor", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 69
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload == {
        "ok": False,
        "error_code": "CHROME_EXECUTABLE_NOT_FOUND",
        "message": "Chrome missing",
        "next_action": "install stable Google Chrome and re-run browser-cli doctor --json",
    }
```

Add this import to `tests/unit/test_cli.py`:

```python
from browser_cli.errors import ChromeExecutableNotFoundError, ProfileUnavailableError
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
uv run pytest tests/unit/test_json_errors.py tests/unit/test_error_hints.py::test_recovery_error_hints tests/unit/test_cli.py::test_json_mode_error_renders_json_to_stdout -v
```

Expected: FAIL because new error classes and renderer are missing.

- [ ] **Step 3: Add error code constants**

Append to `src/browser_cli/error_codes.py`:

```python
WORKSPACE_BINDING_LOST = "WORKSPACE_BINDING_LOST"
EXTENSION_PORT_IN_USE = "EXTENSION_PORT_IN_USE"
CHROME_EXECUTABLE_NOT_FOUND = "CHROME_EXECUTABLE_NOT_FOUND"
HEADLESS_RUNTIME_UNAVAILABLE = "HEADLESS_RUNTIME_UNAVAILABLE"
```

`EXTENSION_UNAVAILABLE` and `EXTENSION_CAPABILITY_INCOMPLETE` already exist; keep their existing constants.

- [ ] **Step 4: Add typed errors**

Append to `src/browser_cli/errors.py` after `OperationFailedError`:

```python
class WorkspaceBindingLostError(OperationFailedError):
    def __init__(self, message: str = "Workspace binding was lost.") -> None:
        super().__init__(message, error_code=error_codes.WORKSPACE_BINDING_LOST)


class ExtensionUnavailableError(OperationFailedError):
    def __init__(self, message: str = "Browser CLI extension is not connected.") -> None:
        super().__init__(message, error_code=error_codes.EXTENSION_UNAVAILABLE)


class ExtensionCapabilityIncompleteError(OperationFailedError):
    def __init__(
        self,
        message: str = "Browser CLI extension is connected but missing required capabilities.",
    ) -> None:
        super().__init__(message, error_code=error_codes.EXTENSION_CAPABILITY_INCOMPLETE)


class ExtensionPortInUseError(OperationFailedError):
    def __init__(self, message: str = "Browser CLI extension listener port is in use.") -> None:
        super().__init__(message, error_code=error_codes.EXTENSION_PORT_IN_USE)


class ChromeExecutableNotFoundError(BrowserUnavailableError):
    def __init__(self, message: str = "Stable Google Chrome was not found.") -> None:
        BrowserCliError.__init__(
            self,
            message,
            exit_codes.BROWSER_UNAVAILABLE,
            error_codes.CHROME_EXECUTABLE_NOT_FOUND,
        )


class HeadlessRuntimeUnavailableError(BrowserUnavailableError):
    def __init__(self, message: str = "Headless browser runtime is unavailable.") -> None:
        BrowserCliError.__init__(
            self,
            message,
            exit_codes.BROWSER_UNAVAILABLE,
            error_codes.HEADLESS_RUNTIME_UNAVAILABLE,
        )
```

- [ ] **Step 5: Add JSON error renderer**

In `src/browser_cli/outputs/json.py`, import the error type and add:

```python
from browser_cli.errors import BrowserCliError


def render_json_error(exc: BrowserCliError, *, next_action: str | None = None) -> str:
    payload: dict[str, Any] = {
        "ok": False,
        "error_code": exc.error_code,
        "message": exc.message,
    }
    if next_action:
        payload["next_action"] = next_action
    return render_json_payload(payload)
```

- [ ] **Step 6: Add error hints**

In `src/browser_cli/cli/error_hints.py`, extend `next_hint_for_error` before the message-based checks:

```python
    if exc.error_code == error_codes.WORKSPACE_BINDING_LOST:
        return "run browser-cli workspace rebuild --json"
    if exc.error_code == error_codes.EXTENSION_UNAVAILABLE:
        return "connect or reload the Browser CLI extension"
    if exc.error_code == error_codes.EXTENSION_CAPABILITY_INCOMPLETE:
        return "reload the Browser CLI extension and run browser-cli recover --json"
    if exc.error_code == error_codes.EXTENSION_PORT_IN_USE:
        return "set BROWSER_CLI_EXTENSION_PORT to a free port or stop the process using it"
    if exc.error_code == error_codes.CHROME_EXECUTABLE_NOT_FOUND:
        return "install stable Google Chrome and re-run browser-cli doctor --json"
    if exc.error_code == error_codes.HEADLESS_RUNTIME_UNAVAILABLE:
        return "set BROWSER_CLI_HEADLESS=1 in container environments and re-run browser-cli doctor --json"
```

- [ ] **Step 7: Render JSON-mode CLI errors from `main()`**

In `src/browser_cli/cli/main.py`, import:

```python
from browser_cli.outputs.json import render_json_error
```

Update the `except BrowserCliError` block:

```python
    except BrowserCliError as exc:
        hint = next_hint_for_error(exc)
        if getattr(args, "json", False):
            sys.stdout.write(render_json_error(exc, next_action=hint))
            return exc.exit_code
        sys.stderr.write(f"Error: {exc}\n")
        if hint:
            sys.stderr.write(f"Next: {hint}\n")
        return exc.exit_code
```

- [ ] **Step 8: Run focused tests**

Run:

```bash
uv run pytest tests/unit/test_json_errors.py tests/unit/test_error_hints.py tests/unit/test_cli.py::test_json_mode_error_renders_json_to_stdout -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

Run:

```bash
git add src/browser_cli/error_codes.py src/browser_cli/errors.py src/browser_cli/cli/error_hints.py src/browser_cli/outputs/json.py src/browser_cli/cli/main.py tests/unit/test_error_hints.py tests/unit/test_json_errors.py tests/unit/test_cli.py
git commit -m "feat: add structured recovery errors"
```

### Task 3: Workspace Rebuild And Recover Commands

**Files:**
- Create: `src/browser_cli/commands/recovery.py`
- Modify: `src/browser_cli/cli/main.py`
- Modify: `src/browser_cli/daemon/app.py`
- Modify: `tests/unit/test_cli.py`
- Create: `tests/unit/test_recovery_commands.py`
- Modify: `tests/unit/test_runtime_presentation.py`

- [ ] **Step 1: Write failing parser tests**

Add to `tests/unit/test_cli.py`:

```python
def test_workspace_rebuild_help_mentions_json(capsys) -> None:
    exit_code = main(["workspace", "rebuild", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--json" in captured.out
    assert "workspace binding" in captured.out.lower()


def test_recover_help_mentions_json(capsys) -> None:
    exit_code = main(["recover", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--json" in captured.out
    assert "recover" in captured.out.lower()
```

- [ ] **Step 2: Write failing recovery command tests**

Create `tests/unit/test_recovery_commands.py`:

```python
from __future__ import annotations

import json
from argparse import Namespace
from unittest.mock import patch

from browser_cli.commands.recovery import run_recover_command, run_workspace_command


def _status_data(binding: str, recommended: str = "none") -> dict[str, object]:
    return {
        "status": "degraded" if recommended != "none" else "healthy",
        "daemon": {"state": "running", "pid": 100, "socket_reachable": True},
        "backend": {
            "active_driver": "extension",
            "extension_connected": True,
            "extension_capability_complete": True,
            "extension_listener": {
                "host": "127.0.0.1",
                "port": 19825,
                "ws_url": "ws://127.0.0.1:19825/ext",
            },
        },
        "browser": {"started": True, "workspace_binding": binding},
        "recovery": {
            "recommended_action": recommended,
            "available_actions": ["refresh-status", "rebuild-workspace-binding"],
        },
    }


def test_workspace_rebuild_json_reports_before_after() -> None:
    statuses = [_status_data("stale", "rebuild-workspace-binding"), _status_data("tracked")]
    with (
        patch("browser_cli.commands.recovery.ensure_daemon_running") as ensure_daemon,
        patch("browser_cli.commands.recovery.collect_stable_status_data", side_effect=statuses),
        patch(
            "browser_cli.commands.recovery.send_command",
            return_value={"ok": True, "data": {"tab_state_reset": True}},
        ) as send_command,
    ):
        payload = json.loads(
            run_workspace_command(Namespace(workspace_subcommand="rebuild", json=True))
        )

    ensure_daemon.assert_called_once_with()
    send_command.assert_called_once_with("workspace-rebuild-binding", {}, start_if_needed=True)
    assert payload["data"]["action_taken"] == "rebuild-workspace-binding"
    assert payload["data"]["before_status"]["browser"]["workspace_binding"] == "stale"
    assert payload["data"]["after_status"]["browser"]["workspace_binding"] == "tracked"
    assert payload["data"]["recovered"] is True


def test_recover_json_can_reload_then_rebuild() -> None:
    statuses = [
        _status_data("absent", "reload"),
        _status_data("stale", "rebuild-workspace-binding"),
        _status_data("tracked"),
    ]
    calls: list[str] = []

    def _send(action: str, args=None, start_if_needed: bool = True):
        calls.append(action)
        return {"ok": True, "data": {}}

    with (
        patch("browser_cli.commands.recovery.ensure_daemon_running"),
        patch("browser_cli.commands.recovery.wait_for_daemon_stop", return_value=True),
        patch("browser_cli.commands.recovery.collect_stable_status_data", side_effect=statuses),
        patch("browser_cli.commands.recovery.send_command", side_effect=_send),
    ):
        payload = json.loads(run_recover_command(Namespace(json=True)))

    assert calls == ["stop", "workspace-rebuild-binding"]
    assert payload["data"]["action_taken"] == "reload+rebuild-workspace-binding"
    assert payload["data"]["recovered"] is True


def test_workspace_rebuild_json_failure_returns_structured_error() -> None:
    with (
        patch("browser_cli.commands.recovery.ensure_daemon_running"),
        patch(
            "browser_cli.commands.recovery.collect_stable_status_data",
            return_value=_status_data("absent", "reconnect-extension"),
        ),
    ):
        payload = json.loads(
            run_workspace_command(Namespace(workspace_subcommand="rebuild", json=True))
        )

    assert payload == {
        "ok": False,
        "error_code": "EXTENSION_UNAVAILABLE",
        "message": "Browser CLI extension is not connected.",
        "next_action": "connect or reload the Browser CLI extension",
    }
```

- [ ] **Step 3: Run failing parser and recovery tests**

Run:

```bash
uv run pytest tests/unit/test_cli.py::test_workspace_rebuild_help_mentions_json tests/unit/test_cli.py::test_recover_help_mentions_json tests/unit/test_recovery_commands.py -v
```

Expected: FAIL because commands and module are missing.

- [ ] **Step 4: Add daemon action**

In `src/browser_cli/daemon/app.py`, add imports:

```python
from browser_cli.errors import (
    BrowserCliError,
    ExtensionCapabilityIncompleteError,
    ExtensionUnavailableError,
    InvalidInputError,
    NoActiveTabError,
    OperationFailedError,
)
```

Add to `_handlers`:

```python
            "workspace-rebuild-binding": self._handle_workspace_rebuild_binding,
```

Add handler after `_handle_runtime_status`:

```python
    async def _handle_workspace_rebuild_binding(self, request: DaemonRequest) -> dict[str, Any]:
        status = await self._state.browser_service.runtime_status(warmup=True)
        extension = dict(status.get("extension") or {})
        if not bool(extension.get("connected")):
            raise ExtensionUnavailableError("Browser CLI extension is not connected.")
        if not bool(extension.get("capability_complete")):
            missing = ", ".join(str(item) for item in extension.get("missing_capabilities") or [])
            suffix = f" Missing capabilities: {missing}." if missing else ""
            raise ExtensionCapabilityIncompleteError(
                "Browser CLI extension is missing required capabilities." + suffix
            )
        return await self._state.browser_service.rebuild_workspace_binding()
```

- [ ] **Step 5: Add CLI recovery module**

Create `src/browser_cli/commands/recovery.py`:

```python
"""Agent-facing runtime recovery commands."""

from __future__ import annotations

from argparse import Namespace
from typing import Any

from browser_cli.cli.error_hints import next_hint_for_error
from browser_cli.commands.status import collect_status_report, status_report_to_json_data
from browser_cli.daemon.client import ensure_daemon_running, send_command, wait_for_daemon_stop
from browser_cli.errors import BrowserCliError, ExtensionUnavailableError, InvalidInputError
from browser_cli.outputs.json import render_json_error, render_json_payload


def run_workspace_command(args: Namespace) -> str:
    if args.workspace_subcommand != "rebuild":
        raise InvalidInputError(f"Unsupported workspace subcommand: {args.workspace_subcommand}")
    if not getattr(args, "json", False):
        raise InvalidInputError("workspace rebuild currently requires --json")
    try:
        return _run_workspace_rebuild_json()
    except BrowserCliError as exc:
        return render_json_error(exc, next_action=next_hint_for_error(exc))


def run_recover_command(args: Namespace) -> str:
    if not getattr(args, "json", False):
        raise InvalidInputError("recover currently requires --json")
    try:
        return render_json_payload({"ok": True, "data": _recover(), "meta": {"action": "recover"}})
    except BrowserCliError as exc:
        return render_json_error(exc, next_action=next_hint_for_error(exc))


def collect_stable_status_data() -> dict[str, Any]:
    return status_report_to_json_data(collect_status_report(warmup=False))


def _run_workspace_rebuild_json() -> str:
    ensure_daemon_running()
    before = collect_stable_status_data()
    _ensure_extension_available(before)
    send_command("workspace-rebuild-binding", {}, start_if_needed=True)
    after = collect_stable_status_data()
    data = _result_payload(
        before=before,
        after=after,
        action_taken="rebuild-workspace-binding",
    )
    return render_json_payload({"ok": True, "data": data, "meta": {"action": "workspace-rebuild"}})


def _recover() -> dict[str, Any]:
    ensure_daemon_running()
    before = collect_stable_status_data()
    actions: list[str] = []
    current = before
    recommended = str(current["recovery"]["recommended_action"])
    if recommended in {"reload", "reconnect-extension"}:
        send_command("stop", {}, start_if_needed=False)
        wait_for_daemon_stop()
        ensure_daemon_running()
        actions.append("reload")
        current = collect_stable_status_data()
    if current["recovery"]["recommended_action"] == "rebuild-workspace-binding":
        send_command("workspace-rebuild-binding", {}, start_if_needed=True)
        actions.append("rebuild-workspace-binding")
        current = collect_stable_status_data()
    action_taken = "+".join(actions) if actions else "none"
    return _result_payload(before=before, after=current, action_taken=action_taken)


def _ensure_extension_available(status: dict[str, Any]) -> None:
    backend = dict(status.get("backend") or {})
    if not bool(backend.get("extension_connected")):
        raise ExtensionUnavailableError("Browser CLI extension is not connected.")


def _result_payload(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    action_taken: str,
) -> dict[str, Any]:
    return {
        "before_status": before,
        "action_taken": action_taken,
        "after_status": after,
        "recovered": after.get("recovery", {}).get("recommended_action") == "none",
    }
```

- [ ] **Step 6: Add parser wiring**

In `src/browser_cli/cli/main.py`, import:

```python
from browser_cli.commands.recovery import run_recover_command, run_workspace_command
```

Add after `reload_parser`:

```python
    workspace_parser = subparsers.add_parser(
        "workspace",
        help="Inspect or repair Browser CLI workspace state.",
        description="Operate on Browser CLI-owned extension workspace binding.",
    )
    workspace_subparsers = workspace_parser.add_subparsers(
        dest="workspace_subcommand", metavar="WORKSPACE_COMMAND"
    )
    workspace_rebuild_parser = workspace_subparsers.add_parser(
        "rebuild",
        help="Rebuild extension workspace binding.",
        description="Rebuild Browser CLI-owned workspace binding through the daemon.",
    )
    workspace_rebuild_parser.add_argument(
        "--json",
        action="store_true",
        help="Return machine-readable recovery result.",
    )
    workspace_rebuild_parser.set_defaults(handler=run_workspace_command)

    recover_parser = subparsers.add_parser(
        "recover",
        help="Recover Browser CLI runtime state.",
        description="Run agent-friendly daemon and workspace recovery.",
    )
    recover_parser.add_argument(
        "--json",
        action="store_true",
        help="Return machine-readable recovery result.",
    )
    recover_parser.set_defaults(handler=run_recover_command)
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
uv run pytest tests/unit/test_cli.py::test_workspace_rebuild_help_mentions_json tests/unit/test_cli.py::test_recover_help_mentions_json tests/unit/test_recovery_commands.py tests/unit/test_runtime_presentation.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add src/browser_cli/cli/main.py src/browser_cli/commands/recovery.py src/browser_cli/daemon/app.py tests/unit/test_cli.py tests/unit/test_recovery_commands.py tests/unit/test_runtime_presentation.py
git commit -m "feat: add workspace recovery commands"
```

### Task 4: Command-Start Preflight Recovery Metadata

**Files:**
- Modify: `src/browser_cli/daemon/browser_service.py`
- Modify: `src/browser_cli/daemon/app.py`
- Modify: `tests/unit/test_daemon_browser_service.py`

- [ ] **Step 1: Write failing preflight tests**

Add to `tests/unit/test_daemon_browser_service.py`:

```python
def test_browser_service_preflight_rebuilds_stale_workspace_binding(
    _patched_browser_service: _FakeExtensionHub,
) -> None:
    async def _run() -> None:
        _patched_browser_service.connect()
        service = browser_service_module.BrowserService()
        await service.begin_command("info")
        meta = await service.end_command()

        assert meta["preflight"]["attempted"] is True
        assert meta["preflight"]["ok"] is True
        assert meta["driver_reason"] == "workspace-binding-rebuilt"

    asyncio.run(_run())


def test_browser_service_preflight_failure_is_reported(
    _patched_browser_service: _FakeExtensionHub,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        _patched_browser_service.connect()
        service = browser_service_module.BrowserService()

        async def _fail_rebuild(self) -> dict[str, object]:
            raise browser_service_module.OperationFailedError("rebuild failed")

        monkeypatch.setattr(_FakeExtensionDriver, "rebuild_workspace_binding", _fail_rebuild)

        await service.begin_command("info")
        meta = await service.end_command()

        assert meta["preflight"]["attempted"] is True
        assert meta["preflight"]["ok"] is False
        assert meta["preflight"]["next_action"] == "browser-cli recover --json"

    asyncio.run(_run())
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
uv run pytest tests/unit/test_daemon_browser_service.py::test_browser_service_preflight_rebuilds_stale_workspace_binding tests/unit/test_daemon_browser_service.py::test_browser_service_preflight_failure_is_reported -v
```

Expected: FAIL because `meta["preflight"]` is missing.

- [ ] **Step 3: Add preflight helpers to `BrowserService`**

In `src/browser_cli/daemon/browser_service.py`, import the new error:

```python
from browser_cli import error_codes
```

Add this method to `BrowserService` near `begin_command`:

```python
    async def _maybe_preflight_workspace_binding(self) -> dict[str, Any] | None:
        if self._driver_name != "extension" or self._command_depth != 0:
            return None
        session = self._extension_hub.session
        if session is None or not session.hello.has_required_capabilities():
            return None
        tabs = await self._tab_runtime_status()
        if int(tabs.get("busy_count") or 0) > 0:
            return None
        workspace_state = await self._extension.workspace_status()
        binding_state = str(workspace_state.get("binding_state") or "absent")
        if binding_state not in {"stale", "absent"}:
            return None
        try:
            await self.rebuild_workspace_binding()
            return {
                "attempted": True,
                "action": "rebuild-workspace-binding",
                "ok": True,
                "before_workspace_binding": binding_state,
                "next_action": None,
            }
        except BrowserCliError as exc:
            return {
                "attempted": True,
                "action": "rebuild-workspace-binding",
                "ok": False,
                "error_code": exc.error_code or error_codes.WORKSPACE_BINDING_LOST,
                "message": exc.message,
                "next_action": "browser-cli recover --json",
            }
```

- [ ] **Step 4: Call preflight from `begin_command`**

Update `begin_command`:

```python
    async def begin_command(self, action: str) -> None:
        await self.ensure_started()
        preflight = await self._maybe_preflight_workspace_binding()
        self._stability.commands_started += 1
        self._stability.active_command = action
        if self._driver_name == "extension":
            session = self._extension_hub.session
            if session is None or not session.hello.has_required_capabilities():
                self._stability.extension_disconnects += 1
                logger.warning(
                    "Extension unavailable at command start; rebinding to playwright for action=%s",
                    action,
                )
                await self._activate_driver("playwright", reason="extension-disconnected-command")
        await self._maybe_apply_pending_rebind()
        self._command_depth += 1
        self._last_runtime_meta = {"driver": self.active_driver_name, "command": action}
        if preflight is not None:
            self._last_runtime_meta["preflight"] = preflight
```

- [ ] **Step 5: Preserve runtime meta on daemon error responses**

In `src/browser_cli/daemon/app.py`, update `_error_response` signature and use:

```python
    def _error_response(
        self,
        exc: BrowserCliError,
        *,
        request: DaemonRequest,
        runtime_meta: dict[str, Any] | None = None,
    ) -> DaemonResponse:
        meta = {
            "action": request.action,
            "agent_id": request.agent_id,
            "driver": self._state.browser_service.active_driver_name,
        }
        if runtime_meta:
            meta.update(runtime_meta)
        return DaemonResponse.failure(
            error_code=exc.error_code,
            error_message=exc.message,
            meta=meta,
        )
```

Update the `except BrowserCliError` call:

```python
        except BrowserCliError as exc:
            if command_started:
                runtime_meta = await self._state.browser_service.end_command()
            return self._error_response(exc, request=request, runtime_meta=runtime_meta)
```

- [ ] **Step 6: Run focused preflight tests**

Run:

```bash
uv run pytest tests/unit/test_daemon_browser_service.py::test_browser_service_preflight_rebuilds_stale_workspace_binding tests/unit/test_daemon_browser_service.py::test_browser_service_preflight_failure_is_reported -v
```

Expected: PASS.

- [ ] **Step 7: Run daemon browser service tests**

Run:

```bash
uv run pytest tests/unit/test_daemon_browser_service.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add src/browser_cli/daemon/browser_service.py src/browser_cli/daemon/app.py tests/unit/test_daemon_browser_service.py
git commit -m "feat: add workspace preflight recovery"
```

### Task 5: Sync `read --json`

**Files:**
- Modify: `src/browser_cli/cli/main.py`
- Modify: `src/browser_cli/commands/read.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Write failing read JSON tests**

Add to `tests/unit/test_cli.py`:

```python
def test_read_help_mentions_json_and_async(capsys) -> None:
    exit_code = main(["read", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--json" in captured.out
    assert "--async" in captured.out


def test_read_json_wraps_body_and_fallback_metadata(capsys) -> None:
    with patch(
        "browser_cli.commands.read.BrowserCliTaskClient.read",
        return_value=ReadResult(
            body="snapshot body",
            used_fallback_profile=True,
            fallback_profile_dir="/tmp/profile",
            fallback_reason="locked",
        ),
    ):
        exit_code = main(["read", "https://example.com", "--snapshot", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload == {
        "ok": True,
        "data": {
            "body": "snapshot body",
            "output_mode": "snapshot",
            "used_fallback_profile": True,
            "fallback_profile_dir": "/tmp/profile",
            "fallback_reason": "locked",
        },
        "meta": {"action": "read"},
    }
    assert captured.err == ""
```

Add `import json` to the top of `tests/unit/test_cli.py` if missing.

- [ ] **Step 2: Run failing tests**

Run:

```bash
uv run pytest tests/unit/test_cli.py::test_read_help_mentions_json_and_async tests/unit/test_cli.py::test_read_json_wraps_body_and_fallback_metadata -v
```

Expected: FAIL because read parser lacks `--json` and `--async`.

- [ ] **Step 3: Add parser flags**

In `src/browser_cli/cli/main.py`, add to `read_parser`:

```python
    read_parser.add_argument(
        "--json",
        action="store_true",
        help="Return machine-readable read result.",
    )
    read_parser.add_argument(
        "--async",
        dest="async_run",
        action="store_true",
        help="Start an async daemon read run and return a run id.",
    )
```

- [ ] **Step 4: Add sync JSON rendering**

In `src/browser_cli/commands/read.py`, import:

```python
from browser_cli.outputs.json import render_json_payload
```

Update `run_read_command`:

```python
def run_read_command(args: Namespace) -> str:
    if bool(getattr(args, "async_run", False)):
        return _run_read_async(args)
    client = BrowserCliTaskClient()
    output_mode = "snapshot" if args.snapshot else "html"
    result = client.read(
        normalize_url(args.url),
        output_mode=output_mode,
        scroll_bottom=bool(args.scroll_bottom),
    )
    if getattr(args, "json", False):
        return render_json_payload(
            {
                "ok": True,
                "data": {
                    "body": result.body,
                    "output_mode": output_mode,
                    "used_fallback_profile": result.used_fallback_profile,
                    "fallback_profile_dir": result.fallback_profile_dir,
                    "fallback_reason": result.fallback_reason,
                },
                "meta": {"action": "read"},
            }
        )
    if result.used_fallback_profile and result.fallback_profile_dir:
        message = (
            "Info: primary Chrome profile unavailable; using fallback profile at "
            f"{result.fallback_profile_dir}"
        )
        if result.fallback_reason:
            message += f". Reason: {result.fallback_reason}"
        sys.stderr.write(message + "\n")
    return render_output(result.body)
```

Add a temporary async guard below it so `--async` has a clear error until Task 6:

```python
def _run_read_async(args: Namespace) -> str:
    from browser_cli.errors import InvalidInputError

    if not getattr(args, "json", False):
        raise InvalidInputError("read --async requires --json")
    raise InvalidInputError("read --async requires the async read run registry task.")
```

- [ ] **Step 5: Run focused read tests**

Run:

```bash
uv run pytest tests/unit/test_cli.py::test_read_help_mentions_json_and_async tests/unit/test_cli.py::test_read_json_wraps_body_and_fallback_metadata tests/unit/test_cli.py::test_fallback_profile_reports_to_stderr -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/browser_cli/cli/main.py src/browser_cli/commands/read.py tests/unit/test_cli.py
git commit -m "feat: add read json output"
```

### Task 6: Async Read Run Registry And `run-*` Commands

**Files:**
- Create: `src/browser_cli/daemon/run_registry.py`
- Modify: `src/browser_cli/daemon/state.py`
- Modify: `src/browser_cli/daemon/app.py`
- Modify: `src/browser_cli/cli/main.py`
- Modify: `src/browser_cli/commands/read.py`
- Create: `src/browser_cli/commands/runs.py`
- Create: `tests/unit/test_daemon_run_registry.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Write failing run registry tests**

Create `tests/unit/test_daemon_run_registry.py`:

```python
from __future__ import annotations

import asyncio

from browser_cli.daemon.run_registry import CommandRunRegistry


def test_run_registry_completes_successful_read() -> None:
    async def _run() -> None:
        async def _read(args: dict[str, object]) -> dict[str, object]:
            assert args["url"] == "https://example.com"
            return {"body": "ok", "used_fallback_profile": False}

        registry = CommandRunRegistry(read_handler=_read)
        started = registry.start_read(
            {
                "url": "https://example.com",
                "output_mode": "html",
                "scroll_bottom": False,
            }
        )
        assert started["status"] == "queued"
        run_id = str(started["run_id"])
        await asyncio.sleep(0)
        status = registry.status(run_id)
        assert status["status"] in {"running", "succeeded"}
        await registry.wait_for_idle()
        status = registry.status(run_id)
        assert status["status"] == "succeeded"
        assert status["result"]["body"] == "ok"
        assert registry.logs(run_id, tail=10)["events"][-1]["event"] == "completed"

    asyncio.run(_run())


def test_run_registry_cancel_marks_run() -> None:
    async def _run() -> None:
        started_event = asyncio.Event()

        async def _read(args: dict[str, object]) -> dict[str, object]:
            started_event.set()
            await asyncio.sleep(60)
            return {"body": "late"}

        registry = CommandRunRegistry(read_handler=_read)
        run_id = str(registry.start_read({"url": "https://example.com"})["run_id"])
        await started_event.wait()
        cancel = registry.cancel(run_id)
        assert cancel["cancel_requested"] is True
        await registry.wait_for_idle()
        assert registry.status(run_id)["status"] == "canceled"

    asyncio.run(_run())


def test_run_registry_not_found() -> None:
    async def _read(args: dict[str, object]) -> dict[str, object]:
        return {}

    registry = CommandRunRegistry(read_handler=_read)
    assert registry.status("run_missing")["status"] == "not_found"
```

- [ ] **Step 2: Write failing parser tests for `run-*`**

Add to `tests/unit/test_cli.py`:

```python
def test_run_status_help_mentions_json(capsys) -> None:
    exit_code = main(["run-status", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--json" in captured.out


def test_run_logs_help_mentions_tail(capsys) -> None:
    exit_code = main(["run-logs", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--tail" in captured.out


def test_run_cancel_help(capsys) -> None:
    exit_code = main(["run-cancel", "--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "run_id" in captured.out
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
uv run pytest tests/unit/test_daemon_run_registry.py tests/unit/test_cli.py::test_run_status_help_mentions_json tests/unit/test_cli.py::test_run_logs_help_mentions_tail tests/unit/test_cli.py::test_run_cancel_help -v
```

Expected: FAIL because registry and parser commands are missing.

- [ ] **Step 4: Add daemon run registry**

Create `src/browser_cli/daemon/run_registry.py`:

```python
"""In-memory daemon command run registry."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

ReadHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class CommandRunRegistry:
    def __init__(self, *, read_handler: ReadHandler) -> None:
        self._read_handler = read_handler
        self._counter = 0
        self._runs: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start_read(self, args: dict[str, Any]) -> dict[str, Any]:
        self._counter += 1
        run_id = f"run_{self._counter:06d}"
        record = {
            "run_id": run_id,
            "command": "read",
            "status": "queued",
            "created_at": time.time(),
            "updated_at": time.time(),
            "args": dict(args),
            "events": [],
            "result": None,
            "error": None,
        }
        self._runs[run_id] = record
        self._event(record, "queued", "Read run queued.")
        self._tasks[run_id] = asyncio.create_task(self._execute_read(run_id))
        return self.status(run_id)

    def status(self, run_id: str) -> dict[str, Any]:
        record = self._runs.get(run_id)
        if record is None:
            return {"run_id": run_id, "status": "not_found", "message": "Run id was not found."}
        return {
            "run_id": record["run_id"],
            "command": record["command"],
            "status": record["status"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "result": record["result"],
            "error": record["error"],
        }

    def logs(self, run_id: str, *, tail: int = 200) -> dict[str, Any]:
        record = self._runs.get(run_id)
        if record is None:
            return {"run_id": run_id, "status": "not_found", "events": []}
        events = list(record["events"])[-max(0, tail):]
        return {"run_id": run_id, "status": record["status"], "events": events}

    def cancel(self, run_id: str) -> dict[str, Any]:
        record = self._runs.get(run_id)
        if record is None:
            return {"run_id": run_id, "status": "not_found", "cancel_requested": False}
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            record["status"] = "cancel_requested"
            self._event(record, "cancel_requested", "Cancellation requested.")
            task.cancel()
            return {"run_id": run_id, "status": "cancel_requested", "cancel_requested": True}
        return {"run_id": run_id, "status": record["status"], "cancel_requested": False}

    async def wait_for_idle(self) -> None:
        tasks = list(self._tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_read(self, run_id: str) -> None:
        record = self._runs[run_id]
        try:
            record["status"] = "running"
            self._event(record, "started", "Read run started.")
            result = await self._read_handler(dict(record["args"]))
            record["status"] = "succeeded"
            record["result"] = dict(result)
            self._event(record, "completed", "Read run completed.")
        except asyncio.CancelledError:
            record["status"] = "canceled"
            self._event(record, "canceled", "Read run canceled.")
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = {"message": str(exc), "type": type(exc).__name__}
            self._event(record, "failed", str(exc))
        finally:
            record["updated_at"] = time.time()

    def _event(self, record: dict[str, Any], event: str, message: str) -> None:
        now = time.time()
        record["updated_at"] = now
        record["events"].append({"at": now, "event": event, "message": message})
```

- [ ] **Step 5: Add registry to daemon state**

In `src/browser_cli/daemon/state.py`, import and initialize:

```python
from browser_cli.daemon.run_registry import CommandRunRegistry
```

Update `DaemonState.__init__` to this complete shape:

```python
class DaemonState:
    def __init__(self) -> None:
        self.tabs = TabRegistry()
        self.browser_service = BrowserService(self.tabs)
        self.run_registry = CommandRunRegistry(
            read_handler=self.browser_service.read_page_from_args
        )
        self.shutdown_event = asyncio.Event()
```

- [ ] **Step 6: Add read handler adapter**

In `src/browser_cli/daemon/browser_service.py`, add:

```python
    async def read_page_from_args(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self.read_page(
            url=str(args.get("url") or ""),
            output_mode=str(args.get("output_mode") or "html"),
            scroll_bottom=bool(args.get("scroll_bottom")),
        )
```

- [ ] **Step 7: Add daemon run handlers**

In `src/browser_cli/daemon/app.py`, add handlers:

```python
            "run-start-read": self._handle_run_start_read,
            "run-status": self._handle_run_status,
            "run-logs": self._handle_run_logs,
            "run-cancel": self._handle_run_cancel,
```

Exclude them from normal browser command preflight in `execute`:

```python
            if request.action not in {
                "runtime-status",
                "stop",
                "run-start-read",
                "run-status",
                "run-logs",
                "run-cancel",
            }:
```

Add handlers:

```python
    async def _handle_run_start_read(self, request: DaemonRequest) -> dict[str, Any]:
        url = self._require_str(request.args, "url")
        return self._state.run_registry.start_read(
            {
                "url": url,
                "output_mode": str(request.args.get("output_mode") or "html"),
                "scroll_bottom": bool(request.args.get("scroll_bottom")),
            }
        )

    async def _handle_run_status(self, request: DaemonRequest) -> dict[str, Any]:
        return self._state.run_registry.status(self._require_str(request.args, "run_id"))

    async def _handle_run_logs(self, request: DaemonRequest) -> dict[str, Any]:
        return self._state.run_registry.logs(
            self._require_str(request.args, "run_id"),
            tail=int(request.args.get("tail") or 200),
        )

    async def _handle_run_cancel(self, request: DaemonRequest) -> dict[str, Any]:
        return self._state.run_registry.cancel(self._require_str(request.args, "run_id"))
```

- [ ] **Step 8: Add CLI run commands and async read start**

Create `src/browser_cli/commands/runs.py`:

```python
"""CLI handlers for daemon async command runs."""

from __future__ import annotations

from argparse import Namespace

from browser_cli.daemon.client import send_command
from browser_cli.outputs.json import render_json_payload


def run_run_status_command(args: Namespace) -> str:
    response = send_command("run-status", {"run_id": args.run_id}, start_if_needed=True)
    return render_json_payload(response)


def run_run_logs_command(args: Namespace) -> str:
    response = send_command(
        "run-logs",
        {"run_id": args.run_id, "tail": int(args.tail)},
        start_if_needed=True,
    )
    return render_json_payload(response)


def run_run_cancel_command(args: Namespace) -> str:
    response = send_command("run-cancel", {"run_id": args.run_id}, start_if_needed=True)
    return render_json_payload(response)
```

In `src/browser_cli/commands/read.py`, replace `_run_read_async`:

```python
def _run_read_async(args: Namespace) -> str:
    from browser_cli.daemon.client import send_command
    from browser_cli.errors import InvalidInputError

    if not getattr(args, "json", False):
        raise InvalidInputError("read --async requires --json")
    output_mode = "snapshot" if args.snapshot else "html"
    response = send_command(
        "run-start-read",
        {
            "url": normalize_url(args.url),
            "output_mode": output_mode,
            "scroll_bottom": bool(args.scroll_bottom),
        },
        start_if_needed=True,
    )
    data = dict(response.get("data") or {})
    if data.get("run_id"):
        data["poll"] = f"browser-cli run-status {data['run_id']} --json"
    return render_json_payload({"ok": True, "data": data, "meta": {"action": "read-async"}})
```

In `src/browser_cli/cli/main.py`, import run handlers and add parsers:

```python
from browser_cli.commands.runs import (
    run_run_cancel_command,
    run_run_logs_command,
    run_run_status_command,
)
```

Add near recovery commands:

```python
    run_status_parser = subparsers.add_parser(
        "run-status",
        help="Show daemon async run status.",
        description="Poll a daemon-side async command run.",
    )
    run_status_parser.add_argument("run_id")
    run_status_parser.add_argument("--json", action="store_true", help="Return JSON status.")
    run_status_parser.set_defaults(handler=run_run_status_command)

    run_logs_parser = subparsers.add_parser(
        "run-logs",
        help="Show daemon async run event logs.",
        description="Show bounded event logs for a daemon-side async command run.",
    )
    run_logs_parser.add_argument("run_id")
    run_logs_parser.add_argument("--tail", type=int, default=200)
    run_logs_parser.set_defaults(handler=run_run_logs_command)

    run_cancel_parser = subparsers.add_parser(
        "run-cancel",
        help="Cancel a daemon async run.",
        description="Request cancellation for a daemon-side async command run.",
    )
    run_cancel_parser.add_argument("run_id")
    run_cancel_parser.set_defaults(handler=run_run_cancel_command)
```

- [ ] **Step 9: Run focused async tests**

Run:

```bash
uv run pytest tests/unit/test_daemon_run_registry.py tests/unit/test_cli.py::test_run_status_help_mentions_json tests/unit/test_cli.py::test_run_logs_help_mentions_tail tests/unit/test_cli.py::test_run_cancel_help -v
```

Expected: PASS.

- [ ] **Step 10: Commit**

Run:

```bash
git add src/browser_cli/daemon/run_registry.py src/browser_cli/daemon/state.py src/browser_cli/daemon/browser_service.py src/browser_cli/daemon/app.py src/browser_cli/cli/main.py src/browser_cli/commands/read.py src/browser_cli/commands/runs.py tests/unit/test_daemon_run_registry.py tests/unit/test_cli.py
git commit -m "feat: add async read run registry"
```

### Task 7: Doctor, Run-Info, Headless, Container, And Extension Port Diagnostics

**Files:**
- Modify: `src/browser_cli/daemon/server.py`
- Modify: `src/browser_cli/extension/session.py`
- Modify: `src/browser_cli/commands/doctor.py`
- Modify: `tests/unit/test_doctor_command.py`
- Modify: `tests/unit/test_extension_transport.py`

- [ ] **Step 1: Write failing doctor diagnostics tests**

Add to `tests/unit/test_doctor_command.py`:

```python
def test_doctor_json_reports_environment(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("BROWSER_CLI_HOME", str(home))
    monkeypatch.setenv("BROWSER_CLI_HEADLESS", "1")
    monkeypatch.setenv("BROWSER_CLI_EXTENSION_HOST", "127.0.0.1")
    monkeypatch.setenv("BROWSER_CLI_EXTENSION_PORT", "19825")
    monkeypatch.setattr("browser_cli.commands.doctor._daemon_runtime_payload", lambda: None)
    monkeypatch.setattr(
        "browser_cli.commands.doctor._chrome_candidates",
        lambda: [{"path": "/usr/bin/google-chrome", "exists": False}],
    )
    monkeypatch.setattr("browser_cli.commands.doctor._is_container", lambda: (True, ["/.dockerenv"]))
    monkeypatch.setattr("browser_cli.commands.doctor._can_bind_extension_port", lambda host, port: (True, None))

    payload = json.loads(run_doctor_command(Namespace(json=True)))

    assert payload["data"]["environment"] == {
        "in_container": True,
        "container_markers": ["/.dockerenv"],
        "headless_env": "1",
        "headless_effective": True,
        "extension_host": "127.0.0.1",
        "extension_port": 19825,
    }
    assert any(check["id"] == "extension_port" for check in payload["data"]["checks"])
    assert any(check["id"] == "headless" for check in payload["data"]["checks"])


def test_doctor_extension_port_reports_bind_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("browser_cli.commands.doctor._daemon_runtime_payload", lambda: None)
    monkeypatch.setattr("browser_cli.commands.doctor._is_container", lambda: (False, []))
    monkeypatch.setattr(
        "browser_cli.commands.doctor._can_bind_extension_port",
        lambda host, port: (False, "Address already in use"),
    )
    report = collect_doctor_report()
    check = next(item for item in report["checks"] if item["id"] == "extension_port")
    assert check["status"] == "warn"
    assert check["error_code"] == "EXTENSION_PORT_IN_USE"
    assert "BROWSER_CLI_EXTENSION_PORT" in check["next"]
```

- [ ] **Step 2: Run failing doctor tests**

Run:

```bash
uv run pytest tests/unit/test_doctor_command.py::test_doctor_json_reports_environment tests/unit/test_doctor_command.py::test_doctor_extension_port_reports_bind_failure -v
```

Expected: FAIL because environment and port checks are missing.

- [ ] **Step 3: Add error_code field to DoctorCheck**

In `src/browser_cli/commands/doctor.py`, update `DoctorCheck`:

```python
@dataclass(slots=True, frozen=True)
class DoctorCheck:
    id: str
    status: str
    summary: str
    details: str | None = None
    next: str | None = None
    error_code: str | None = None
```

- [ ] **Step 4: Add environment collection and checks**

In `src/browser_cli/commands/doctor.py`, import:

```python
import socket
from browser_cli import error_codes
from browser_cli.browser.models import HEADLESS_ENV, default_headless
```

Update `collect_doctor_report`:

```python
def collect_doctor_report() -> dict[str, Any]:
    app_paths = get_app_paths()
    daemon_payload = _daemon_runtime_payload()
    environment = _environment_payload(app_paths)
    checks = [
        _package_check(),
        _chrome_check(),
        _chrome_candidates_check(),
        _playwright_check(),
        _home_check(app_paths),
        _managed_profile_check(),
        _daemon_check(app_paths),
        _automation_service_check(app_paths),
        _extension_check(daemon_payload),
        _headless_check(environment),
        _container_check(environment),
        _extension_port_check(app_paths),
    ]
    overall_status = "pass"
    if any(item.status == "fail" for item in checks):
        overall_status = "fail"
    elif any(item.status == "warn" for item in checks):
        overall_status = "warn"
    return {
        "overall_status": overall_status,
        "environment": environment,
        "checks": [asdict(item) for item in checks],
    }
```

Add helpers:

```python
def _environment_payload(app_paths: AppPaths) -> dict[str, Any]:
    in_container, markers = _is_container()
    return {
        "in_container": in_container,
        "container_markers": markers,
        "headless_env": os.environ.get(HEADLESS_ENV),
        "headless_effective": default_headless(),
        "extension_host": app_paths.extension_host,
        "extension_port": app_paths.extension_port,
    }


def _is_container() -> tuple[bool, list[str]]:
    markers: list[str] = []
    for marker in ("/.dockerenv", "/run/.containerenv"):
        if Path(marker).exists():
            markers.append(marker)
    cgroup = Path("/proc/1/cgroup")
    if cgroup.exists():
        with contextlib.suppress(OSError):
            content = cgroup.read_text(encoding="utf-8", errors="ignore")
            if any(token in content for token in ("docker", "kubepods", "containerd", "podman")):
                markers.append("/proc/1/cgroup")
    return bool(markers), markers


def _headless_check(environment: dict[str, Any]) -> DoctorCheck:
    if environment["in_container"] and not environment["headless_effective"]:
        return DoctorCheck(
            id="headless",
            status="warn",
            summary="Container environment detected but headless mode is not enabled.",
            details=f"{HEADLESS_ENV}={environment['headless_env']}",
            next="set BROWSER_CLI_HEADLESS=1 and re-run browser-cli doctor --json",
            error_code=error_codes.HEADLESS_RUNTIME_UNAVAILABLE,
        )
    return DoctorCheck(
        id="headless",
        status="pass",
        summary="Headless configuration is explicit or not required.",
        details=f"effective={environment['headless_effective']}",
    )


def _container_check(environment: dict[str, Any]) -> DoctorCheck:
    if environment["in_container"]:
        return DoctorCheck(
            id="container",
            status="pass",
            summary="Container environment detected.",
            details=", ".join(environment["container_markers"]),
        )
    return DoctorCheck(id="container", status="pass", summary="No container markers detected.")


def _can_bind_extension_port(host: str, port: int) -> tuple[bool, str | None]:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((host, port))
    except OSError as exc:
        return False, str(exc)
    finally:
        probe.close()
    return True, None


def _extension_port_check(app_paths: AppPaths) -> DoctorCheck:
    ok, reason = _can_bind_extension_port(app_paths.extension_host, app_paths.extension_port)
    endpoint = f"{app_paths.extension_host}:{app_paths.extension_port}"
    if ok:
        return DoctorCheck(
            id="extension_port",
            status="pass",
            summary="Extension listener port can be bound.",
            details=endpoint,
        )
    return DoctorCheck(
        id="extension_port",
        status="warn",
        summary="Extension listener port cannot be bound.",
        details=f"{endpoint}: {reason}",
        next="set BROWSER_CLI_EXTENSION_PORT to a free port or stop the process using it",
        error_code=error_codes.EXTENSION_PORT_IN_USE,
    )
```

Also import `contextlib` at the top.

- [ ] **Step 5: Add Chrome candidates check**

In `src/browser_cli/commands/doctor.py`, replace `_discover_chrome_executable` candidate construction with reusable helper:

```python
def _chrome_candidates() -> list[dict[str, Any]]:
    candidates: list[Path] = []
    if sys.platform == "darwin":
        candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    elif sys.platform.startswith("linux"):
        for binary_name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            binary_path = shutil.which(binary_name)
            if binary_path:
                candidates.append(Path(binary_path))
        candidates.extend(
            [
                Path("/opt/google/chrome/chrome"),
                Path("/usr/bin/google-chrome"),
                Path("/usr/bin/google-chrome-stable"),
                Path("/usr/bin/chromium"),
                Path("/usr/bin/chromium-browser"),
            ]
        )
    else:
        return []
    seen: set[str] = set()
    payload: list[dict[str, Any]] = []
    for candidate in candidates:
        text = str(candidate)
        if text in seen:
            continue
        seen.add(text)
        payload.append({"path": text, "exists": candidate.exists()})
    return payload


def _chrome_candidates_check() -> DoctorCheck:
    candidates = _chrome_candidates()
    details = ", ".join(
        f"{item['path']}={'yes' if item['exists'] else 'no'}" for item in candidates
    )
    return DoctorCheck(
        id="chrome_candidates",
        status="pass" if candidates else "warn",
        summary="Chrome candidate paths were inspected.",
        details=details or "no candidates for this platform",
    )
```

Update `_discover_chrome_executable` to iterate `_chrome_candidates()` and raise:

```python
    for candidate in _chrome_candidates():
        path = Path(str(candidate["path"]))
        if bool(candidate["exists"]) and path.exists():
            return path
    raise RuntimeError("Stable Google Chrome was not found on this machine.")
```

Update `_chrome_check` failure to include `error_code=error_codes.CHROME_EXECUTABLE_NOT_FOUND`.

- [ ] **Step 6: Add run-info facts**

In `src/browser_cli/daemon/server.py`, import:

```python
from browser_cli.browser.models import default_headless
```

Add fields to `write_run_info` payload:

```python
                    "extension_host": app_paths.extension_host,
                    "extension_port": app_paths.extension_port,
                    "extension_ws_url": app_paths.extension_ws_url,
                    "headless": default_headless(),
```

- [ ] **Step 7: Wrap extension listener bind failure**

In `src/browser_cli/extension/session.py`, import:

```python
import errno
from browser_cli.errors import ExtensionPortInUseError, OperationFailedError
```

Wrap the `websockets.serve` call in `ensure_started`:

```python
            try:
                self._server = await websockets.serve(
                    self._handle_websocket,
                    host=app_paths.extension_host,
                    port=app_paths.extension_port,
                    ping_interval=None,
                    ping_timeout=None,
                    process_request=self._process_request,
                )
            except OSError as exc:
                if exc.errno == errno.EADDRINUSE:
                    raise ExtensionPortInUseError(
                        f"Extension listener port is in use: {app_paths.extension_host}:{app_paths.extension_port}"
                    ) from exc
                raise OperationFailedError(f"Extension listener failed to start: {exc}") from exc
```

Remove the original unwrapped `self._server = await websockets.serve(...)` block.

- [ ] **Step 8: Run focused doctor tests**

Run:

```bash
uv run pytest tests/unit/test_doctor_command.py -v
```

Expected: PASS.

- [ ] **Step 9: Run extension transport tests**

Run:

```bash
uv run pytest tests/unit/test_extension_transport.py -v
```

Expected: PASS.

- [ ] **Step 10: Commit**

Run:

```bash
git add src/browser_cli/daemon/server.py src/browser_cli/extension/session.py src/browser_cli/commands/doctor.py tests/unit/test_doctor_command.py tests/unit/test_extension_transport.py
git commit -m "feat: improve runtime environment diagnostics"
```

### Task 8: AGENTS Guidance, Full Validation, And Guard Pass

**Files:**
- Modify: `AGENTS.md`
- Modify: `scripts/guards/docs_sync.py` only when `scripts/guard.sh` reports a docs-sync expectation failure for the new public CLI surface

- [ ] **Step 1: Update AGENTS.md durable navigation**

In `AGENTS.md`, add durable notes under `System Snapshot`:

```markdown
- `browser-cli status --json` is the stable agent-facing runtime status surface.
- `browser-cli workspace rebuild --json` is the precise non-interactive extension workspace binding repair command.
- `browser-cli recover --json` is the broader agent recovery command and may reload before rebuilding workspace binding.
- `browser-cli read --async --json` creates a daemon-memory read run; `run-status`, `run-logs`, and `run-cancel` operate on that run id until daemon restart.
- Extension listener endpoint is configured by `BROWSER_CLI_EXTENSION_HOST` and `BROWSER_CLI_EXTENSION_PORT` and is reported by status/run-info/doctor.
```

Add under `Common Navigation Paths`:

```markdown
- If the user reports that agent automation cannot decide whether Browser CLI is healthy:
  inspect `src/browser_cli/commands/status.py`, `src/browser_cli/daemon/runtime_presentation.py`, and `src/browser_cli/commands/recovery.py`; `status --json` should remain a stable projection of daemon-owned presentation.
- If the user reports stale or absent extension workspace binding:
  inspect `src/browser_cli/commands/recovery.py`, `src/browser_cli/daemon/app.py::_handle_workspace_rebuild_binding`, and `src/browser_cli/daemon/browser_service.py::rebuild_workspace_binding`; safe repair is `browser-cli workspace rebuild --json` or `browser-cli recover --json`.
- If the user reports async read polling issues:
  inspect `src/browser_cli/daemon/run_registry.py`, `src/browser_cli/commands/runs.py`, and `src/browser_cli/commands/read.py`; first-version run ids are daemon-memory only and do not survive daemon restart.
- If the user reports container/headless or extension listener port problems:
  inspect `src/browser_cli/commands/doctor.py`, `src/browser_cli/daemon/server.py`, `src/browser_cli/extension/session.py`, and `src/browser_cli/constants.py`.
```

- [ ] **Step 2: Run lint**

Run:

```bash
scripts/lint.sh
```

Expected: exits 0.

- [ ] **Step 3: Run tests**

Run:

```bash
scripts/test.sh
```

Expected: exits 0.

- [ ] **Step 4: Run guard**

Run:

```bash
scripts/guard.sh
```

Expected: exits 0. If docs sync guard fails because the public CLI surface changed, update the guard expectation file it names, then rerun `scripts/guard.sh`.

- [ ] **Step 5: Run full check**

Run:

```bash
scripts/check.sh
```

Expected: exits 0.

- [ ] **Step 6: Commit docs and guard updates**

Run:

```bash
git add AGENTS.md scripts/guards
git commit -m "docs: document agent runtime recovery surfaces"
```

If `scripts/guards` has no changes, run:

```bash
git add AGENTS.md
git commit -m "docs: document agent runtime recovery surfaces"
```

## Self-Review Checklist

- Spec coverage:
  - `status --json`: Task 1
  - workspace rebuild and recover commands: Task 3
  - command preflight: Task 4
  - structured errors and hints: Task 2
  - sync `read --json`: Task 5
  - async read run registry and `run-*`: Task 6
  - doctor/container/headless/port/run-info: Task 7
  - AGENTS update and validation: Task 8
- Type consistency:
  - Status JSON uses `status_report_to_json_data(report)`.
  - CLI recovery uses `collect_stable_status_data()`.
  - Daemon async registry uses `CommandRunRegistry`.
  - Async read daemon action is `run-start-read`.
  - Recovery daemon action is `workspace-rebuild-binding`.
- Scope check:
  - The plan does not add persisted async run history.
  - The plan does not add async support for commands beyond `read`.
  - The plan does not introduce a new browser runtime or public explore command.
