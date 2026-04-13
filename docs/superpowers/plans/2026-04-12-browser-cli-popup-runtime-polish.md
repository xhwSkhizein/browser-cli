# Browser CLI Popup Runtime Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daemon-owned runtime presentation model, expose it to the extension popup through the extension listener, and upgrade the popup into a human-facing runtime observer with a narrow set of safe recovery actions.

**Architecture:** Keep one runtime truth path. `BrowserService` and daemon action handlers continue to own raw runtime facts; a new daemon presentation module classifies those facts into stable runtime semantics; `browser-cli status` and the extension popup render the same presentation snapshot. The popup gets that snapshot from the extension listener over lightweight HTTP endpoints and only offers `refresh`, `reconnect extension`, and `rebuild workspace binding`.

**Tech Stack:** Python 3.10, pytest, websockets, Chrome extension JavaScript, Node built-in test runner, Browser CLI guard/lint scripts

---

## File Structure

- Modify: `src/browser_cli/daemon/browser_service.py`
  - Persist recent driver transition facts, expose richer runtime facts, and add a safe workspace-rebuild method that coordinates daemon tab state with extension-owned workspace state.
- Modify: `src/browser_cli/tabs/registry.py`
  - Add an explicit registry-clear helper for daemon-coordinated workspace rebuilds.
- Create: `src/browser_cli/daemon/runtime_presentation.py`
  - Convert raw runtime facts into the shared presentation snapshot used by CLI and popup.
- Modify: `src/browser_cli/daemon/app.py`
  - Add the presentation snapshot to `runtime-status` and surface compact runtime notes in command metadata.
- Modify: `src/browser_cli/commands/status.py`
  - Reuse the shared presentation snapshot for top-level state, summary, and guidance instead of maintaining a separate classifier.
- Modify: `src/browser_cli/extension/session.py`
  - Add extension-listener HTTP endpoints for popup status reads and workspace-rebuild control, backed by daemon callbacks.
- Modify: `src/browser_cli/drivers/_extension/state_actions.py`
  - Add extension driver helpers for live workspace status and daemon-coordinated workspace rebuild.
- Modify: `browser-cli-extension/src/background.js`
  - Fetch daemon-owned runtime snapshots from the extension listener, cache them, and expose popup messages for refresh and workspace rebuild.
- Modify: `browser-cli-extension/src/background/workspace.js`
  - Add `workspace-status` and `workspace-rebuild-binding` extension actions.
- Modify: `browser-cli-extension/popup.html`
  - Replace the current connection-only panel with runtime summary, execution path, workspace ownership, and recovery sections.
- Modify: `browser-cli-extension/src/popup.js`
  - Render the shared runtime snapshot and bind the three allowed popup actions.
- Modify: `browser-cli-extension/src/popup.css`
  - Style the richer runtime cards and action states.
- Create: `browser-cli-extension/src/popup_view.js`
  - Hold pure rendering helpers so popup view logic can be tested without Chrome APIs.
- Create: `browser-cli-extension/tests/popup_view.test.js`
  - Node-based tests for popup view-model rendering and action visibility.
- Modify: `tests/unit/test_daemon_browser_service.py`
  - Cover live workspace facts, last transition facts, and safe workspace rebuild behavior.
- Create: `tests/unit/test_runtime_presentation.py`
  - Cover runtime state classification, summary reason, guidance, and allowed actions.
- Modify: `tests/unit/test_lifecycle_commands.py`
  - Verify `browser-cli status` consumes the shared presentation snapshot correctly.
- Modify: `tests/unit/test_extension_transport.py`
  - Verify the extension listener HTTP status and workspace-rebuild endpoints.
- Modify: `scripts/lint.sh`
  - Run the popup Node tests in addition to `node --check`.
- Modify: `docs/smoke-checklist.md`
  - Add popup runtime-observer checks and safe recovery checks.
- Modify: `AGENTS.md`
  - Record the new runtime presentation model, popup role, and extension-listener HTTP status/control path.

### Task 1: Add richer raw runtime facts in BrowserService and the extension workspace layer

**Files:**
- Modify: `src/browser_cli/daemon/browser_service.py`
- Modify: `src/browser_cli/tabs/registry.py`
- Modify: `src/browser_cli/drivers/_extension/state_actions.py`
- Modify: `browser-cli-extension/src/background/workspace.js`
- Test: `tests/unit/test_daemon_browser_service.py`

- [ ] **Step 1: Write the failing BrowserService tests**

```python
def test_browser_service_runtime_status_includes_last_transition_and_live_workspace(
    _patched_browser_service: _FakeExtensionHub,
) -> None:
    async def _scenario() -> None:
        tabs = TabRegistry()
        service = browser_service_module.BrowserService(tabs)
        await service.ensure_started()

        page = await service.new_tab(url="https://example.com/start")
        await tabs.add_tab(
            page_id=page["page_id"],
            owner_agent_id="agent-a",
            url=page["url"],
            title=page["title"],
        )

        await service.begin_command("html")
        _patched_browser_service.connect()
        await asyncio.sleep(0)
        await service.end_command()

        status = await service.runtime_status()
        assert status["last_transition"] == {
            "driver_changed_from": "playwright",
            "driver_changed_to": "extension",
            "driver_reason": "extension-connected",
            "state_reset": True,
        }
        assert status["workspace_window_state"]["binding_state"] == "tracked"
        assert status["workspace_window_state"]["managed_tab_count"] == 1

        await service.stop()

    asyncio.run(_scenario())


def test_browser_service_rebuild_workspace_binding_clears_tab_snapshot_state(
    _patched_browser_service: _FakeExtensionHub,
) -> None:
    async def _scenario() -> None:
        _patched_browser_service.connect()
        tabs = TabRegistry()
        service = browser_service_module.BrowserService(tabs)
        await service.begin_command("open")
        meta = await service.end_command()
        assert meta["driver"] == "extension"

        page = await service.new_tab(url="https://example.com/rebind")
        await tabs.add_tab(
            page_id=page["page_id"],
            owner_agent_id="agent-a",
            url=page["url"],
            title=page["title"],
        )

        rebuilt = await service.rebuild_workspace_binding()
        assert rebuilt["rebuilt"] is True
        assert rebuilt["workspace_window_state"]["binding_state"] == "tracked"
        assert rebuilt["tab_state_reset"] is True

        records, active_by_agent = await tabs.snapshot_state()
        assert records == []
        assert active_by_agent == {}
        await service.stop()

    asyncio.run(_scenario())
```

- [ ] **Step 2: Run the BrowserService tests to verify they fail**

Run: `pytest tests/unit/test_daemon_browser_service.py::test_browser_service_runtime_status_includes_last_transition_and_live_workspace tests/unit/test_daemon_browser_service.py::test_browser_service_rebuild_workspace_binding_clears_tab_snapshot_state -q`

Expected: FAIL with `AttributeError` or assertion failures because `last_transition`, live workspace facts, and `rebuild_workspace_binding()` do not exist yet.

- [ ] **Step 3: Add live workspace status and rebuild support in the extension driver and background handlers**

```python
# src/browser_cli/drivers/_extension/state_actions.py
class ExtensionDriverStateMixin:
    async def workspace_status(self) -> dict[str, Any]:
        session = await self._require_session()
        payload = await session.send_request("workspace-status", {})
        return {
            "window_id": payload.get("window_id"),
            "tab_count": int(payload.get("tab_count") or 0),
            "managed_tab_count": int(payload.get("managed_tab_count") or 0),
            "binding_state": str(payload.get("binding_state") or "absent"),
        }

    async def rebuild_workspace_binding(self) -> dict[str, Any]:
        session = await self._require_session()
        payload = await session.send_request("workspace-rebuild-binding", {})
        self._page_to_tab.clear()
        self._tab_to_page.clear()
        self._active_page_id = None
        return {
            "rebuilt": bool(payload.get("rebuilt")),
            "workspace_window_state": {
                "window_id": payload.get("window_id"),
                "tab_count": int(payload.get("tab_count") or 0),
                "managed_tab_count": int(payload.get("managed_tab_count") or 0),
                "binding_state": str(payload.get("binding_state") or "absent"),
            },
        }
```

```javascript
// browser-cli-extension/src/background/workspace.js
async function buildWorkspaceStatus(context) {
  const windowId = context.state.workspaceWindowId;
  if (windowId === null) {
    return { window_id: null, tab_count: 0, managed_tab_count: 0, binding_state: 'absent' };
  }

  try {
    const tabs = await chrome.tabs.query({ windowId });
    const managedTabs = tabs.filter((tab) => tab.id !== undefined && context.state.managedTabIds.has(tab.id));
    return {
      window_id: windowId,
      tab_count: tabs.length,
      managed_tab_count: managedTabs.length,
      binding_state: managedTabs.length > 0 ? 'tracked' : 'stale',
    };
  } catch (_error) {
    context.state.workspaceWindowId = null;
    context.state.managedTabIds.clear();
    context.state.pageIdByTabId.clear();
    return { window_id: null, tab_count: 0, managed_tab_count: 0, binding_state: 'absent' };
  }
}

export function createWorkspaceHandlers(context) {
  return {
    async 'workspace-status'() {
      return await buildWorkspaceStatus(context);
    },
    async 'workspace-rebuild-binding'() {
      if (context.state.workspaceWindowId !== null) {
        try {
          await chrome.windows.remove(context.state.workspaceWindowId);
        } catch (_error) {
          // Ignore already-closed workspace windows.
        }
      }
      context.state.workspaceWindowId = null;
      context.state.managedTabIds.clear();
      context.state.pageIdByTabId.clear();
      await context.ensureWorkspaceWindow('about:blank');
      return {
        rebuilt: true,
        ...(await buildWorkspaceStatus(context)),
      };
    },
```

- [ ] **Step 4: Persist last transition facts and add daemon-coordinated workspace rebuild in BrowserService**

```python
# src/browser_cli/daemon/browser_service.py
class BrowserService:
    def __init__(
        self,
        tabs: TabRegistry | None = None,
        chrome_environment: ChromeEnvironment | None = None,
        *,
        headless: bool | None = None,
    ) -> None:
        self._tabs = tabs or TabRegistry()
        self._playwright = PlaywrightDriver(
            chrome_environment=chrome_environment, headless=headless
        )
        self._extension_hub = ExtensionHub()
        self._extension = ExtensionDriver(self._extension_hub)
        self._last_transition: dict[str, Any] | None = None

    async def runtime_status(self, *, warmup: bool = False) -> dict[str, Any]:
        if warmup:
            await self.ensure_started()
        extension_health = await self._extension.health()
        playwright_health = await self._playwright.health()
        workspace_window_state = (
            await self._extension.workspace_status()
            if extension_health.details.get("connected")
            else {"window_id": None, "tab_count": 0, "managed_tab_count": 0, "binding_state": "absent"}
        )
        return {
            "browser_started": self._driver is not None,
            "active_driver": self._driver_name,
            "profile_source": profile_source,
            "profile_dir": profile_dir,
            "profile_directory": profile_directory,
            "playwright": {
                "available": playwright_health.available,
                "details": playwright_details,
            },
            "extension": {
                "available": extension_health.available,
                "connected": bool(extension_details.get("connected")),
                "capability_complete": bool(extension_details.get("capability_complete")),
                "missing_capabilities": list(extension_details.get("missing_capabilities") or []),
                "details": extension_details,
            },
            "workspace_window_state": workspace_window_state,
            "pending_rebind": (
                {
                    "target": self._pending_driver,
                    "reason": self._pending_reason,
                }
                if self._pending_driver
                else None
            ),
            "last_transition": dict(self._last_transition or {}),
        }

    async def rebuild_workspace_binding(self) -> dict[str, Any]:
        if self._driver_name != "extension":
            raise OperationFailedError(
                "Workspace binding rebuild is only available while extension mode is active.",
                error_code="WORKSPACE_REBUILD_UNAVAILABLE",
            )
        rebuilt = await self._extension.rebuild_workspace_binding()
        self._snapshot_registry.clear()
        await self._tabs.clear()
        self._last_transition = {
            "driver_changed_from": self._driver_name,
            "driver_changed_to": self._driver_name,
            "driver_reason": "workspace-binding-rebuilt",
            "state_reset": True,
        }
        return {"tab_state_reset": True, **rebuilt}

    async def _activate_driver(self, driver_name: str, *, reason: str) -> None:
        if old_driver_name and old_driver_name != driver_name:
            self._last_transition = {
                "driver_changed_from": old_driver_name,
                "driver_changed_to": driver_name,
                "driver_reason": reason,
                "state_reset": state_reset,
            }
```

```python
# src/browser_cli/tabs/registry.py
class TabRegistry:
    async def clear(self) -> None:
        async with self._lock:
            self._tabs.clear()
            self._active_tab_by_agent.clear()
```

- [ ] **Step 5: Run the BrowserService tests to verify they pass**

Run: `pytest tests/unit/test_daemon_browser_service.py::test_browser_service_runtime_status_includes_last_transition_and_live_workspace tests/unit/test_daemon_browser_service.py::test_browser_service_rebuild_workspace_binding_clears_tab_snapshot_state -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_daemon_browser_service.py src/browser_cli/daemon/browser_service.py src/browser_cli/tabs/registry.py src/browser_cli/drivers/_extension/state_actions.py browser-cli-extension/src/background/workspace.js
git commit -m "feat: add runtime workspace facts"
```

### Task 2: Add the daemon-owned runtime presentation model

**Files:**
- Create: `src/browser_cli/daemon/runtime_presentation.py`
- Modify: `src/browser_cli/daemon/app.py`
- Test: `tests/unit/test_runtime_presentation.py`

- [ ] **Step 1: Write the failing presentation-model tests**

```python
from browser_cli.daemon.runtime_presentation import build_runtime_presentation


def test_build_runtime_presentation_marks_safe_point_fallback_as_recovering() -> None:
    raw_status = {
        "browser_started": True,
        "active_driver": "extension",
        "pending_rebind": {"target": "playwright", "reason": "extension-disconnected-waiting-command"},
        "extension": {
            "connected": False,
            "capability_complete": False,
            "missing_capabilities": [],
        },
        "workspace_window_state": {
            "window_id": 91,
            "tab_count": 1,
            "managed_tab_count": 1,
            "binding_state": "tracked",
        },
        "tabs": {"count": 1, "busy_count": 0, "records": [], "active_by_agent": {}},
        "last_transition": {},
    }

    presentation = build_runtime_presentation(raw_status)

    assert presentation["overall_state"] == "recovering"
    assert presentation["summary_reason"] == (
        "Extension disconnected; Browser CLI will switch to Playwright at the next safe point."
    )
    assert presentation["available_actions"] == ["refresh-status", "reconnect-extension"]


def test_build_runtime_presentation_marks_workspace_binding_loss_as_degraded() -> None:
    raw_status = {
        "browser_started": True,
        "active_driver": "extension",
        "pending_rebind": None,
        "extension": {
            "connected": True,
            "capability_complete": True,
            "missing_capabilities": [],
        },
        "workspace_window_state": {
            "window_id": 91,
            "tab_count": 0,
            "managed_tab_count": 0,
            "binding_state": "stale",
        },
        "tabs": {"count": 0, "busy_count": 0, "records": [], "active_by_agent": {}},
        "last_transition": {},
    }

    presentation = build_runtime_presentation(raw_status)

    assert presentation["overall_state"] == "degraded"
    assert presentation["available_actions"] == [
        "refresh-status",
        "reconnect-extension",
        "rebuild-workspace-binding",
    ]
    assert presentation["workspace_state"]["binding_state"] == "stale"
```

- [ ] **Step 2: Run the presentation-model tests to verify they fail**

Run: `pytest tests/unit/test_runtime_presentation.py -q`

Expected: FAIL with `ModuleNotFoundError` because `runtime_presentation.py` does not exist yet.

- [ ] **Step 3: Implement the shared runtime presentation builder**

```python
# src/browser_cli/daemon/runtime_presentation.py
from __future__ import annotations

from typing import Any


def build_runtime_presentation(raw_status: dict[str, Any]) -> dict[str, Any]:
    pending_rebind = dict(raw_status.get("pending_rebind") or {})
    extension = dict(raw_status.get("extension") or {})
    workspace = dict(raw_status.get("workspace_window_state") or {})
    last_transition = dict(raw_status.get("last_transition") or {})

    overall_state = _classify_state(raw_status, extension, workspace, pending_rebind)
    return {
        "overall_state": overall_state,
        "summary_reason": _summary_reason(overall_state, extension, workspace, pending_rebind),
        "execution_path": {
            "active_driver": raw_status.get("active_driver") or "not-started",
            "pending_rebind": pending_rebind or None,
            "safe_point_wait": bool(pending_rebind),
            "last_transition": last_transition or None,
        },
        "workspace_state": {
            "window_id": workspace.get("window_id"),
            "tab_count": int(workspace.get("tab_count") or 0),
            "managed_tab_count": int(workspace.get("managed_tab_count") or 0),
            "binding_state": str(workspace.get("binding_state") or "absent"),
            "busy_tab_count": int((raw_status.get("tabs") or {}).get("busy_count") or 0),
        },
        "recovery_guidance": _guidance(overall_state, raw_status, extension, workspace, pending_rebind),
        "available_actions": _available_actions(raw_status, extension, workspace),
    }
```

- [ ] **Step 4: Attach the presentation snapshot to `runtime-status`**

```python
# src/browser_cli/daemon/app.py
from browser_cli.daemon.runtime_presentation import build_runtime_presentation

    async def _handle_runtime_status(self, request: DaemonRequest) -> dict[str, Any]:
        warmup = bool(request.args.get("warmup"))
        browser = await self._state.browser_service.runtime_status(warmup=warmup)
        records, active_by_agent = await self._state.tabs.snapshot_state()
        raw_status = {
            **browser,
            "tabs": {
                "count": len(records),
                "busy_count": sum(1 for record in records if record.busy is not None),
                "active_by_agent": active_by_agent,
                "records": [
                    {
                        "page_id": record.page_id,
                        "owner_agent_id": record.owner_agent_id,
                        "url": record.url,
                        "title": record.title,
                        "busy": record.busy is not None,
                        "last_snapshot_id": record.last_snapshot_id,
                    }
                    for record in records
                ],
            },
        }
        return {
            **raw_status,
            "presentation": build_runtime_presentation(raw_status),
        }
```

- [ ] **Step 5: Run the new presentation-model tests**

Run: `pytest tests/unit/test_runtime_presentation.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_runtime_presentation.py src/browser_cli/daemon/runtime_presentation.py src/browser_cli/daemon/app.py
git commit -m "feat: add runtime presentation model"
```

### Task 3: Align `browser-cli status` and command metadata with the shared presentation snapshot

**Files:**
- Modify: `src/browser_cli/commands/status.py`
- Modify: `src/browser_cli/daemon/app.py`
- Test: `tests/unit/test_lifecycle_commands.py`

- [ ] **Step 1: Write the failing lifecycle/status tests**

```python
def test_collect_status_report_uses_daemon_presentation_snapshot(tmp_path: Path) -> None:
    run_info = {
        "pid": 123,
        "package_version": "0.1.0",
        "runtime_version": "2026-04-10-dual-driver-extension-v1",
    }
    runtime_status = {
        "browser_started": True,
        "active_driver": "playwright",
        "profile_source": "managed",
        "profile_dir": str(tmp_path / ".browser-cli/default-profile"),
        "profile_directory": "Default",
        "extension": {
            "connected": False,
            "capability_complete": False,
            "missing_capabilities": [],
        },
        "pending_rebind": {"target": "playwright", "reason": "extension-disconnected-waiting-command"},
        "workspace_window_state": {"window_id": None, "tab_count": 0, "managed_tab_count": 0, "binding_state": "absent"},
        "tabs": {"count": 0, "busy_count": 0, "records": [], "active_by_agent": {}},
        "presentation": {
            "overall_state": "recovering",
            "summary_reason": "Extension disconnected; Browser CLI will switch to Playwright at the next safe point.",
            "execution_path": {"active_driver": "playwright", "pending_rebind": {"target": "playwright", "reason": "extension-disconnected-waiting-command"}, "safe_point_wait": True, "last_transition": None},
            "workspace_state": {"window_id": None, "tab_count": 0, "managed_tab_count": 0, "binding_state": "absent", "busy_tab_count": 0},
            "recovery_guidance": ["Agent can continue; Browser CLI is waiting for a safe-point rebind."],
            "available_actions": ["refresh-status", "reconnect-extension"],
        },
    }
    with (
        patch("browser_cli.commands.status.get_app_paths", return_value=_fake_paths(tmp_path)),
        patch("browser_cli.commands.status.read_run_info", return_value=run_info),
        patch("browser_cli.commands.status.probe_socket", return_value=True),
        patch("browser_cli.commands.status.send_command", return_value={"ok": True, "data": runtime_status}),
    ):
        report = collect_status_report()
        text = run_status_command(Namespace())

    assert report.overall_status == "recovering"
    assert report.presentation["summary_reason"].startswith("Extension disconnected")
    assert "Summary:" in text
    assert "Available actions: refresh-status, reconnect-extension" in text
```

- [ ] **Step 2: Run the lifecycle/status test to verify it fails**

Run: `pytest tests/unit/test_lifecycle_commands.py::test_collect_status_report_uses_daemon_presentation_snapshot -q`

Expected: FAIL because `StatusReport` does not carry `presentation` and the renderer does not print the summary or available actions.

- [ ] **Step 3: Refactor `status.py` to consume the daemon presentation snapshot**

```python
# src/browser_cli/commands/status.py
@dataclass(slots=True)
class StatusReport:
    overall_status: str
    daemon_state: str
    runtime: dict[str, Any]
    daemon: dict[str, Any]
    backend: dict[str, Any]
    browser: dict[str, Any]
    guidance: list[str]
    presentation: dict[str, Any] = field(default_factory=dict)
    workflow_service: dict[str, Any] = field(default_factory=dict)
    live_error: str | None = None

def collect_status_report(*, warmup: bool = False) -> StatusReport:
    app_paths = get_app_paths()
    run_info = read_run_info()
    socket_exists = app_paths.socket_path.exists()
    socket_reachable = probe_socket()
    compatibility: bool | None = None
    if run_info is not None:
        compatibility = run_info_is_compatible(run_info)
    daemon_state = _classify_daemon_state(
        run_info=run_info,
        socket_exists=socket_exists,
        socket_reachable=socket_reachable,
        compatibility=compatibility,
    )
    live_payload: dict[str, Any] | None = None
    live_error: str | None = None
    if socket_reachable and compatibility is not False:
        try:
            response = send_command("runtime-status", {"warmup": warmup}, start_if_needed=False)
            live_payload = dict(response.get("data") or {})
        except BrowserCliError as exc:
            live_error = str(exc)
    runtime_section = {
        "home": str(app_paths.home),
        "socket": str(app_paths.socket_path),
    }
    daemon_section = {
        "state": daemon_state,
        "socket_exists": socket_exists,
        "socket_reachable": socket_reachable,
        "runtime_compatibility": compatibility,
    }
    workflow_service_section = {"running": False, "pid": None, "url": None}
    backend_section = _build_backend_section(live_payload, live_error=live_error)
    browser_section = _build_browser_section(live_payload)
    presentation = dict((live_payload or {}).get("presentation") or {})
    overall_status = (
        str(presentation.get("overall_state") or "")
        or _classify_overall_status(
            daemon_state=daemon_state,
            compatibility=compatibility,
            live_payload=live_payload,
            live_error=live_error,
        )
    )
    guidance = list(
        presentation.get("recovery_guidance")
        or _build_guidance(
            overall_status=overall_status,
            daemon_state=daemon_state,
            live_payload=live_payload,
            live_error=live_error,
        )
    )
    return StatusReport(
        overall_status=overall_status,
        daemon_state=daemon_state,
        runtime=runtime_section,
        daemon=daemon_section,
        backend=backend_section,
        browser=browser_section,
        presentation=presentation,
        guidance=guidance,
        workflow_service=workflow_service_section,
        live_error=live_error,
    )

def render_status_report(report: StatusReport) -> str:
    summary_reason = report.presentation.get("summary_reason") or "-"
    available_actions = ", ".join(report.presentation.get("available_actions") or []) or "none"
    lines = [
        f"Status: {report.overall_status}",
        "",
        f"Summary: {summary_reason}",
        "Runtime",
        f"  home: {report.runtime['home']}",
        f"  socket: {report.runtime['socket']}",
        "",
        "Guidance",
    ]
    for item in report.guidance:
        lines.append(f"- {item}")
    lines.extend(["", f"Available actions: {available_actions}"])
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Add a compact `runtime_note` to daemon command metadata when a transition is important**

```python
# src/browser_cli/daemon/app.py
            if command_started:
                runtime_meta = await self._state.browser_service.end_command()
                meta.update(runtime_meta)
                if runtime_meta.get("driver_reason") == "extension-connected":
                    meta["runtime_note"] = "Browser CLI restored extension mode at a safe point."
                elif runtime_meta.get("driver_reason") == "workspace-binding-rebuilt":
                    meta["runtime_note"] = "Browser CLI rebuilt its owned workspace binding."
```

- [ ] **Step 5: Run the lifecycle/status tests**

Run: `pytest tests/unit/test_lifecycle_commands.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_lifecycle_commands.py src/browser_cli/commands/status.py src/browser_cli/daemon/app.py
git commit -m "feat: align status with runtime presentation"
```

### Task 4: Expose daemon runtime and workspace rebuild through the extension listener HTTP surface

**Files:**
- Modify: `src/browser_cli/extension/session.py`
- Modify: `tests/unit/test_extension_transport.py`

- [ ] **Step 1: Write the failing extension-listener endpoint tests**

```python
def test_extension_hub_serves_runtime_status_snapshot(monkeypatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / ".browser-cli-runtime"))
        monkeypatch.setenv(EXTENSION_PORT_ENV, str(_unused_port()))

        hub = ExtensionHub(status_provider=lambda: {"presentation": {"overall_state": "healthy"}})
        await hub.ensure_started()
        app_paths = get_app_paths()

        reader, writer = await asyncio.open_connection(app_paths.extension_host, app_paths.extension_port)
        writer.write(
            (
                f"GET /ext/runtime-status HTTP/1.1\r\n"
                f"Host: {app_paths.extension_host}:{app_paths.extension_port}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
        )
        await writer.drain()
        response = await reader.read(-1)
        writer.close()
        await writer.wait_closed()

        assert b"200 ok" in response.lower()
        assert b'"overall_state": "healthy"' in response
        await hub.stop()

    asyncio.run(_scenario())


def test_extension_hub_posts_workspace_rebuild(monkeypatch, tmp_path: Path) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / ".browser-cli-runtime"))
        monkeypatch.setenv(EXTENSION_PORT_ENV, str(_unused_port()))

        hub = ExtensionHub(
            status_provider=lambda: {"presentation": {"overall_state": "degraded"}},
            workspace_rebuild_handler=lambda: {
                "rebuilt": True,
                "presentation": {"overall_state": "healthy"},
            },
        )
        await hub.ensure_started()
        app_paths = get_app_paths()

        reader, writer = await asyncio.open_connection(app_paths.extension_host, app_paths.extension_port)
        writer.write(
            (
                f"POST /ext/workspace-rebuild HTTP/1.1\r\n"
                f"Host: {app_paths.extension_host}:{app_paths.extension_port}\r\n"
                "Content-Length: 0\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
        )
        await writer.drain()
        response = await reader.read(-1)
        writer.close()
        await writer.wait_closed()

        assert b"200 ok" in response.lower()
        assert b'"rebuilt": true' in response.lower()
        await hub.stop()

    asyncio.run(_scenario())
```

- [ ] **Step 2: Run the extension transport tests to verify they fail**

Run: `pytest tests/unit/test_extension_transport.py::test_extension_hub_serves_runtime_status_snapshot tests/unit/test_extension_transport.py::test_extension_hub_posts_workspace_rebuild -q`

Expected: FAIL because `ExtensionHub` does not accept callbacks and `/ext/runtime-status` or `/ext/workspace-rebuild` do not exist.

- [ ] **Step 3: Add callback-backed HTTP endpoints to the extension listener**

```python
# src/browser_cli/extension/session.py
class ExtensionHub:
    PROBE_PATH = "/ext"
    STATUS_PATH = "/ext/runtime-status"
    REBUILD_PATH = "/ext/workspace-rebuild"

    def __init__(
        self,
        *,
        status_provider: Callable[[], Awaitable[dict[str, Any]] | dict[str, Any]] | None = None,
        workspace_rebuild_handler: Callable[[], Awaitable[dict[str, Any]] | dict[str, Any]] | None = None,
    ) -> None:
        self._server: websockets.server.Serve | None = None
        self._session: ExtensionSession | None = None
        self._session_ready = asyncio.Event()
        self._started = False
        self._lock = asyncio.Lock()
        self._session_changed = asyncio.Event()
        self._status_provider = status_provider
        self._workspace_rebuild_handler = workspace_rebuild_handler

    async def get_runtime_status_payload(self) -> dict[str, Any]:
        if self._status_provider is None:
            return {"ok": False, "error": "status unavailable"}
        payload = self._status_provider()
        if asyncio.iscoroutine(payload):
            payload = await payload
        return dict(payload)

    async def rebuild_workspace_payload(self) -> dict[str, Any]:
        if self._workspace_rebuild_handler is None:
            return {"ok": False, "error": "workspace rebuild unavailable"}
        payload = self._workspace_rebuild_handler()
        if asyncio.iscoroutine(payload):
            payload = await payload
        return dict(payload)
```

```python
# src/browser_cli/daemon/browser_service.py
class BrowserService:
    def __init__(
        self,
        tabs: TabRegistry | None = None,
        chrome_environment: ChromeEnvironment | None = None,
        *,
        headless: bool | None = None,
    ) -> None:
        self._tabs = tabs or TabRegistry()
        self._playwright = PlaywrightDriver(
            chrome_environment=chrome_environment, headless=headless
        )
        self._extension_hub = ExtensionHub(
            status_provider=self.runtime_status_for_popup,
            workspace_rebuild_handler=self.rebuild_workspace_binding,
        )
        self._extension = ExtensionDriver(self._extension_hub)

    async def runtime_status_for_popup(self) -> dict[str, Any]:
        raw_status = await self.runtime_status(warmup=False)
        return {
            **raw_status,
            "presentation": build_runtime_presentation(raw_status),
        }
```

- [ ] **Step 4: Extend `_process_request` to serve JSON for popup status and workspace rebuild**

```python
# src/browser_cli/extension/session.py
    async def _process_request(
        self, connection_or_path: ServerConnection | str, request_or_headers: Request | Headers
    ) -> Response | None:
        if hasattr(request_or_headers, "headers"):
            request = request_or_headers
            path = request.path
            headers = request.headers
        else:
            path = str(connection_or_path)
            headers = request_or_headers
            request = Request(path=path, headers=headers)
        if self._is_websocket_upgrade(headers):
            return None
        if path == self.PROBE_PATH:
            return self._build_response(
                HTTPStatus.UPGRADE_REQUIRED,
                b"Browser CLI extension endpoint expects a WebSocket upgrade.\n",
                upgrade="websocket",
            )
        if path == self.STATUS_PATH:
            payload = await self.get_runtime_status_payload()
            body = json.dumps(payload).encode("utf-8")
            return self._build_json_response(HTTPStatus.OK, body)
        if path == self.REBUILD_PATH and request.method == "POST":
            payload = await self.rebuild_workspace_payload()
            body = json.dumps(payload).encode("utf-8")
            return self._build_json_response(HTTPStatus.OK, body)
        return self._build_response(HTTPStatus.NOT_FOUND, b"Not Found\n")
```

- [ ] **Step 5: Run the extension transport tests**

Run: `pytest tests/unit/test_extension_transport.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_extension_transport.py src/browser_cli/extension/session.py src/browser_cli/daemon/browser_service.py
git commit -m "feat: expose popup runtime endpoints"
```

### Task 5: Rebuild the popup UI around the runtime presentation snapshot and add popup view tests

**Files:**
- Modify: `browser-cli-extension/src/background.js`
- Modify: `browser-cli-extension/popup.html`
- Modify: `browser-cli-extension/src/popup.js`
- Modify: `browser-cli-extension/src/popup.css`
- Create: `browser-cli-extension/src/popup_view.js`
- Create: `browser-cli-extension/tests/popup_view.test.js`
- Modify: `scripts/lint.sh`

- [ ] **Step 1: Write the failing popup view tests**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';

import { buildPopupViewModel } from '../src/popup_view.js';

test('buildPopupViewModel exposes runtime summary and actions', () => {
  const view = buildPopupViewModel({
    daemonHost: '127.0.0.1',
    daemonPort: 19825,
    connectionStatus: 'connected',
    presentation: {
      overall_state: 'recovering',
      summary_reason: 'Extension disconnected; Browser CLI will switch to Playwright at the next safe point.',
      execution_path: {
        active_driver: 'extension',
        pending_rebind: { target: 'playwright', reason: 'extension-disconnected-waiting-command' },
        safe_point_wait: true,
        last_transition: null,
      },
      workspace_state: {
        window_id: 91,
        tab_count: 1,
        managed_tab_count: 1,
        binding_state: 'tracked',
        busy_tab_count: 0,
      },
      recovery_guidance: ['Agent can continue; Browser CLI is waiting for a safe-point rebind.'],
      available_actions: ['refresh-status', 'reconnect-extension'],
    },
  });

  assert.equal(view.badgeLabel, 'recovering');
  assert.equal(view.summaryReason, 'Extension disconnected; Browser CLI will switch to Playwright at the next safe point.');
  assert.deepEqual(view.actions, [
    { id: 'refresh-status', domId: 'refreshStatus', label: 'Refresh Status', enabled: true },
    { id: 'reconnect-extension', domId: 'reconnectNow', label: 'Reconnect Extension', enabled: true },
    { id: 'rebuild-workspace-binding', domId: 'rebuildWorkspace', label: 'Rebuild Workspace', enabled: false },
  ]);
});
```

- [ ] **Step 2: Run the popup view tests to verify they fail**

Run: `node --test browser-cli-extension/tests/popup_view.test.js`

Expected: FAIL because `popup_view.js` does not exist yet.

- [ ] **Step 3: Fetch the daemon snapshot in extension background and add pure popup view helpers**

```javascript
// browser-cli-extension/src/background.js
function buildRuntimeStatusUrl(host, port) {
  return `http://${host}:${port}/ext/runtime-status`;
}

function buildWorkspaceRebuildUrl(host, port) {
  return `http://${host}:${port}/ext/workspace-rebuild`;
}

async function fetchRuntimePresentation(config) {
  const response = await fetch(buildRuntimeStatusUrl(config.host, config.port), {
    method: 'GET',
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`Runtime status request failed: ${response.status}`);
  }
  return await response.json();
}

async function buildStatusSnapshot() {
  const config = await loadDaemonConfig();
  const runtimeSnapshot = await fetchRuntimePresentation(config).catch(() => null);
  return {
    connectionStatus: state.runtimeState.connectionStatus,
    daemonHost: config.host,
    daemonPort: Number(config.port),
    lastError: state.runtimeState.lastError,
    lastConnectedAt: state.runtimeState.lastConnectedAt,
    presentation: runtimeSnapshot?.presentation || null,
    runtimeSnapshot,
  };
}
```

```javascript
// browser-cli-extension/src/popup_view.js
export function buildPopupViewModel(status) {
  const presentation = status.presentation || {};
  const actions = new Set(presentation.available_actions || []);
  return {
    badgeLabel: presentation.overall_state || status.connectionStatus || 'disconnected',
    daemonAddress: `${status.daemonHost}:${status.daemonPort}`,
    summaryReason: presentation.summary_reason || 'Waiting for Browser CLI runtime status.',
    executionPath: presentation.execution_path || {},
    workspaceState: presentation.workspace_state || {},
    guidance: presentation.recovery_guidance || ['Open Browser CLI to initialize runtime state.'],
    actions: [
      { id: 'refresh-status', domId: 'refreshStatus', label: 'Refresh Status', enabled: true },
      { id: 'reconnect-extension', domId: 'reconnectNow', label: 'Reconnect Extension', enabled: actions.has('reconnect-extension') || !presentation.available_actions },
      { id: 'rebuild-workspace-binding', domId: 'rebuildWorkspace', label: 'Rebuild Workspace', enabled: actions.has('rebuild-workspace-binding') },
    ],
  };
}
```

- [ ] **Step 4: Replace the popup markup and rendering to show runtime summary, execution path, workspace ownership, and recovery**

```html
<!-- browser-cli-extension/popup.html -->
<section class="card">
  <h2>Runtime Summary</h2>
  <p id="summary-reason" class="summary-text">Waiting for Browser CLI runtime status.</p>
  <dl class="meta-list">
    <div class="meta-row">
      <dt>Daemon</dt>
      <dd id="daemon-address">127.0.0.1:19825</dd>
    </div>
    <div class="meta-row">
      <dt>Driver</dt>
      <dd id="execution-driver">-</dd>
    </div>
    <div class="meta-row">
      <dt>Pending Rebind</dt>
      <dd id="execution-rebind">none</dd>
    </div>
  </dl>
</section>

<section class="card">
  <h2>Workspace Ownership</h2>
  <dl class="meta-list">
    <div class="meta-row">
      <dt>Binding</dt>
      <dd id="workspace-binding">absent</dd>
    </div>
    <div class="meta-row">
      <dt>Window</dt>
      <dd id="workspace-window">none</dd>
    </div>
    <div class="meta-row">
      <dt>Tabs</dt>
      <dd id="workspace-tabs">0</dd>
    </div>
  </dl>
</section>

<section class="card">
  <h2>Recovery</h2>
  <ul id="recovery-guidance" class="guidance-list"></ul>
  <div class="actions actions-stack">
    <button id="refresh-status" class="button button-secondary" type="button">Refresh Status</button>
    <button id="reconnect-now" class="button" type="button">Reconnect Extension</button>
    <button id="rebuild-workspace" class="button button-secondary" type="button">Rebuild Workspace</button>
  </div>
</section>
```

```javascript
// browser-cli-extension/src/popup.js
import { buildPopupViewModel } from './popup_view.js';

function renderStatus(status) {
  const view = buildPopupViewModel(status);
  els.badge.textContent = view.badgeLabel;
  els.daemonAddress.textContent = view.daemonAddress;
  els.summaryReason.textContent = view.summaryReason;
  els.executionDriver.textContent = view.executionPath.active_driver || 'not-started';
  els.executionRebind.textContent = view.executionPath.pending_rebind
    ? `${view.executionPath.pending_rebind.target} (${view.executionPath.pending_rebind.reason})`
    : 'none';
  els.workspaceBinding.textContent = view.workspaceState.binding_state || 'absent';
  els.workspaceWindow.textContent = view.workspaceState.window_id == null ? 'none' : `window ${view.workspaceState.window_id}`;
  els.workspaceTabs.textContent = String(view.workspaceState.tab_count || 0);
  els.recoveryGuidance.replaceChildren(...view.guidance.map((text) => {
    const item = document.createElement('li');
    item.textContent = text;
    return item;
  }));
  for (const action of view.actions) {
    els[action.domId].disabled = !action.enabled;
  }
}
```

- [ ] **Step 5: Add popup background handlers for refresh and workspace rebuild, then run popup tests**

```javascript
// browser-cli-extension/src/background.js
async function rebuildWorkspaceBinding() {
  const config = await loadDaemonConfig();
  const response = await fetch(buildWorkspaceRebuildUrl(config.host, config.port), {
    method: 'POST',
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`Workspace rebuild failed: ${response.status}`);
  }
  return await buildStatusSnapshot();
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'refresh-status') {
    void buildStatusSnapshot().then(sendResponse);
    return true;
  }
  if (message?.type === 'rebuild-workspace') {
    void rebuildWorkspaceBinding().then(sendResponse);
    return true;
  }
  return false;
});
```

Run: `node --test browser-cli-extension/tests/popup_view.test.js`

Expected: PASS

- [ ] **Step 6: Update lint to run popup Node tests and commit**

```bash
# scripts/lint.sh
if command -v node >/dev/null 2>&1; then
  while IFS= read -r js_file; do
    node --check "$js_file"
  done < <(find browser-cli-extension -type f -name '*.js' | sort)
  node --test browser-cli-extension/tests/popup_view.test.js
fi
```

```bash
git add browser-cli-extension/src/background.js browser-cli-extension/popup.html browser-cli-extension/src/popup.js browser-cli-extension/src/popup.css browser-cli-extension/src/popup_view.js browser-cli-extension/tests/popup_view.test.js scripts/lint.sh
git commit -m "feat: add popup runtime observer"
```

### Task 6: Update durable docs and run repository verification

**Files:**
- Modify: `docs/smoke-checklist.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Update the smoke checklist for popup runtime observation and safe recovery**

```markdown
## Popup Runtime Checks

- Open the Browser CLI extension popup while extension mode is healthy.
- Confirm the popup shows `Runtime Summary`, `Execution Path`, `Workspace Ownership`, and `Recovery`.
- Disconnect the extension and confirm the popup reports a recovering or degraded runtime state rather than only `disconnected`.
- Confirm `Refresh Status` updates the runtime summary without mutating Browser CLI state.
- Confirm `Reconnect Extension` retries the extension transport and refreshes the runtime snapshot.
- Confirm `Rebuild Workspace` only rebuilds Browser CLI-owned workspace state and does not touch arbitrary user tabs.
```

- [ ] **Step 2: Update `AGENTS.md` with the new runtime presentation and popup guidance**

```markdown
- `runtime-status` now includes a daemon-owned presentation snapshot used by both `browser-cli status` and the extension popup.
- The extension popup is a human-facing runtime observer and light recovery surface. It must not define a second runtime state machine or replace Agent feedback through command `meta` and `runtime-status`.
- Popup daemon status reads and workspace rebuild requests flow through the extension listener HTTP surface under `src/browser_cli/extension/session.py`; keep popup UI logic out of that state interpretation path.
```

- [ ] **Step 3: Run targeted tests for all touched areas**

Run: `pytest tests/unit/test_daemon_browser_service.py tests/unit/test_runtime_presentation.py tests/unit/test_lifecycle_commands.py tests/unit/test_extension_transport.py -q`

Expected: PASS

- [ ] **Step 4: Run repository lint and guards**

Run: `scripts/lint.sh`

Expected: PASS

Run: `scripts/guard.sh`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/smoke-checklist.md AGENTS.md
git commit -m "docs: document popup runtime polish"
```

## Self-Review

- Spec coverage:
  - Daemon-owned runtime presentation model: covered by Tasks 1-3.
  - Popup runtime observer and safe actions: covered by Tasks 4-5.
  - Agent truth remaining in command `meta` and `runtime-status`: covered by Task 3.
  - Safe workspace rebuild without touching arbitrary user tabs: covered by Tasks 1 and 4, then verified in Task 6 smoke updates.
  - Durable repo guidance updates: covered by Task 6.
- Placeholder scan:
  - No `TBD`, `TODO`, “write tests later”, or “similar to previous task” shortcuts remain.
- Type consistency:
  - The plan consistently uses `presentation`, `overall_state`, `summary_reason`, `execution_path`, `workspace_state`, `recovery_guidance`, and `available_actions`.
  - The popup action ids are consistently `refresh-status`, `reconnect-extension`, and `rebuild-workspace-binding`.
