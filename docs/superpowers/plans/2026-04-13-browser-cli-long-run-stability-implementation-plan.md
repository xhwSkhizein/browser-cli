# Browser CLI Long-Run Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the minimum daemon-owned observability and repeatable validation loops needed to prove Browser CLI runtime stays honest, recoverable, and bounded across repeated daemon, rebind, workspace, and artifact activity.

**Architecture:** Extend the existing `runtime-status -> runtime_presentation -> status/popup` truth path with a compact stability snapshot sourced from `BrowserService`, then validate that truth path through loop-oriented unit tests, one fixture-backed daemon residency integration test, and explicit real-Chrome smoke guidance. Keep the work inside the current lifecycle surfaces instead of adding a new control plane.

**Tech Stack:** Python 3.10, pytest, Playwright-backed integration tests, websockets extension transport, Browser CLI daemon lifecycle commands, Markdown docs

---

## File Structure

- Modify: `src/browser_cli/daemon/browser_service.py`
  - Own a compact long-run stability snapshot: active command, command depth, command/rebind/rebuild counts, disconnect count, cleanup failure facts.
- Modify: `src/browser_cli/daemon/runtime_presentation.py`
  - Fold the stability snapshot into the shared daemon-owned presentation model and classify cleanup-failure drift as degraded.
- Modify: `src/browser_cli/commands/status.py`
  - Render the new stability snapshot in the top-level lifecycle output without inventing a second interpretation path.
- Modify: `tests/unit/test_daemon_browser_service.py`
  - Lock the raw runtime-status stability metrics and fake-driver rebind/workspace loops.
- Modify: `tests/unit/test_runtime_presentation.py`
  - Lock presentation semantics for cleanup-failure drift and surfaced stability facts.
- Modify: `tests/unit/test_lifecycle_commands.py`
  - Lock the human-readable `status` rendering for the new stability section.
- Modify: `tests/unit/test_extension_transport.py`
  - Lock extension artifact cleanup boundedness across a disconnect + next-request round-trip.
- Create: `tests/integration/test_runtime_stability.py`
  - Add one fixture-backed daemon residency loop that repeatedly exercises `status`, `open`, `snapshot`, `html`, `close`, and `reload`.
- Modify: `docs/smoke-checklist.md`
  - Add a dedicated long-run runtime section for real workstation validation.
- Modify: `AGENTS.md`
  - Add the recurring long-run stability triage path so future agents jump to the right files first.

### Task 1: Add BrowserService Stability Metrics

**Files:**
- Modify: `src/browser_cli/daemon/browser_service.py`
- Test: `tests/unit/test_daemon_browser_service.py`

- [ ] **Step 1: Write the failing BrowserService stability test**

```python
def test_browser_service_runtime_status_tracks_stability_metrics(
    _patched_browser_service: _FakeExtensionHub,
) -> None:
    async def _scenario() -> None:
        _patched_browser_service.connect()
        tabs = TabRegistry()
        service = browser_service_module.BrowserService(tabs)

        await service.begin_command("info")
        await service.end_command()

        _patched_browser_service.disconnect()
        await service.begin_command("tabs")
        await service.end_command()

        _patched_browser_service.connect()
        await service.begin_command("info")
        await service.end_command()

        rebuilt = await service.rebuild_workspace_binding()
        assert rebuilt["tab_state_reset"] is True

        status = await service.runtime_status()
        assert status["stability"] == {
            "active_command": None,
            "command_depth": 0,
            "commands_started": 3,
            "driver_switches": 2,
            "workspace_rebuilds": 1,
            "extension_disconnects": 1,
            "cleanup_failures": 0,
            "last_cleanup_error": None,
        }

        await service.stop()

    asyncio.run(_scenario())
```

- [ ] **Step 2: Run the BrowserService test to verify it fails**

Run: `pytest tests/unit/test_daemon_browser_service.py::test_browser_service_runtime_status_tracks_stability_metrics -q`
Expected: FAIL with `KeyError: 'stability'` or an assertion failure because `runtime_status()` does not expose long-run metrics yet.

- [ ] **Step 3: Add the stability snapshot to BrowserService**

```python
from dataclasses import dataclass


@dataclass(slots=True)
class _StabilityMetrics:
    commands_started: int = 0
    driver_switches: int = 0
    workspace_rebuilds: int = 0
    extension_disconnects: int = 0
    cleanup_failures: int = 0
    last_cleanup_error: str | None = None
    active_command: str | None = None

    def snapshot(self, *, command_depth: int) -> dict[str, Any]:
        return {
            "active_command": self.active_command,
            "command_depth": command_depth,
            "commands_started": self.commands_started,
            "driver_switches": self.driver_switches,
            "workspace_rebuilds": self.workspace_rebuilds,
            "extension_disconnects": self.extension_disconnects,
            "cleanup_failures": self.cleanup_failures,
            "last_cleanup_error": self.last_cleanup_error,
        }
```

```python
self._stability = _StabilityMetrics()
```

```python
async def begin_command(self, action: str) -> None:
    await self.ensure_started()
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


async def end_command(self) -> dict[str, Any]:
    self._command_depth = max(0, self._command_depth - 1)
    if self._command_depth == 0:
        self._stability.active_command = None
        await self._maybe_apply_pending_rebind()
    meta = dict(self._last_runtime_meta)
    self._last_runtime_meta = {}
    return meta
```

```python
async def _stop_driver_for_transition(self, driver_name: str | None) -> None:
    try:
        if driver_name == "extension":
            await self._extension.stop()
        elif driver_name == "playwright":
            await self._playwright.stop()
    except Exception as exc:
        self._stability.cleanup_failures += 1
        self._stability.last_cleanup_error = str(exc)
        logger.warning("Driver stop failed for %s during transition: %s", driver_name, exc)
```

```python
if old_driver_name == "extension":
    await self._stop_driver_for_transition("extension")
elif old_driver_name == "playwright":
    await self._stop_driver_for_transition("playwright")
self._driver = None
self._driver_name = None
if driver_name == "extension":
    await self._extension.ensure_started()
    self._driver = self._extension
else:
    await self._playwright.ensure_started()
    self._driver = self._playwright
self._driver_name = driver_name
self._snapshot_registry.clear()
await self._tabs.clear_snapshot_state()
if old_driver_name and old_driver_name != driver_name:
    self._stability.driver_switches += 1
    self._last_transition = {
        "driver_changed_from": old_driver_name,
        "driver_changed_to": driver_name,
        "driver_reason": reason,
        "state_reset": state_reset,
    }
```

```python
async def rebuild_workspace_binding(self) -> dict[str, Any]:
    await self.ensure_started()
    if self._driver_name != "extension":
        raise OperationFailedError(
            "Workspace binding rebuild is only available in extension mode."
        )
    rebuilt = await self._extension.rebuild_workspace_binding()
    self._snapshot_registry.clear()
    await self._tabs.clear()
    self._stability.workspace_rebuilds += 1
    self._last_transition = {
        "driver_changed_from": "extension",
        "driver_changed_to": "extension",
        "driver_reason": "workspace-binding-rebuilt",
        "state_reset": True,
    }
    return {
        **rebuilt,
        "tab_state_reset": True,
    }
```

```python
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
    "last_transition": (
        dict(self._last_transition) if self._last_transition is not None else None
    ),
    "pending_rebind": (
        {
            "target": self._pending_driver,
            "reason": self._pending_reason,
        }
        if self._pending_driver
        else None
    ),
    "tabs": await self._tab_runtime_status(),
    "stability": self._stability.snapshot(command_depth=self._command_depth),
}
```

- [ ] **Step 4: Run the BrowserService test to verify it passes**

Run: `pytest tests/unit/test_daemon_browser_service.py::test_browser_service_runtime_status_tracks_stability_metrics -q`
Expected: PASS

- [ ] **Step 5: Commit the BrowserService metrics task**

```bash
git add src/browser_cli/daemon/browser_service.py tests/unit/test_daemon_browser_service.py
git commit -m "feat: track runtime stability metrics"
```

### Task 2: Surface Stability Metrics Through Runtime Presentation And Status

**Files:**
- Modify: `src/browser_cli/daemon/runtime_presentation.py`
- Modify: `src/browser_cli/commands/status.py`
- Test: `tests/unit/test_runtime_presentation.py`
- Test: `tests/unit/test_lifecycle_commands.py`

- [ ] **Step 1: Write the failing presentation and status tests**

```python
def test_build_runtime_presentation_marks_cleanup_failures_as_degraded() -> None:
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
            "tab_count": 1,
            "managed_tab_count": 1,
            "binding_state": "tracked",
        },
        "tabs": {"count": 1, "busy_count": 0, "records": [], "active_by_agent": {}},
        "last_transition": {},
        "stability": {
            "active_command": None,
            "command_depth": 0,
            "commands_started": 7,
            "driver_switches": 2,
            "workspace_rebuilds": 0,
            "extension_disconnects": 1,
            "cleanup_failures": 2,
            "last_cleanup_error": "No tab with id: 685338567.",
        },
    }

    presentation = build_runtime_presentation(raw_status)

    assert presentation["overall_state"] == "degraded"
    assert "cleanup failures" in presentation["summary_reason"]
    assert "browser-cli reload" in presentation["recovery_guidance"][0]
    assert presentation["stability"]["cleanup_failures"] == 2
```

```python
def test_collect_status_report_renders_stability_section(tmp_path: Path) -> None:
    run_info = {
        "pid": 123,
        "package_version": "0.1.0",
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
            "binding_state": "tracked",
        },
        "tabs": {"count": 1, "busy_count": 0, "records": [], "active_by_agent": {}},
        "last_transition": None,
        "stability": {
            "active_command": None,
            "command_depth": 0,
            "commands_started": 7,
            "driver_switches": 2,
            "workspace_rebuilds": 1,
            "extension_disconnects": 1,
            "cleanup_failures": 2,
            "last_cleanup_error": "No tab with id: 685338567.",
        },
        "presentation": {
            "overall_state": "degraded",
            "summary_reason": "Browser CLI recorded recent cleanup failures during runtime transitions.",
            "execution_path": {
                "active_driver": "extension",
                "pending_rebind": None,
                "safe_point_wait": False,
                "last_transition": None,
            },
            "workspace_state": {
                "window_id": 91,
                "tab_count": 1,
                "managed_tab_count": 1,
                "binding_state": "tracked",
                "busy_tab_count": 0,
            },
            "stability": {
                "active_command": None,
                "command_depth": 0,
                "commands_started": 7,
                "driver_switches": 2,
                "workspace_rebuilds": 1,
                "extension_disconnects": 1,
                "cleanup_failures": 2,
                "last_cleanup_error": "No tab with id: 685338567.",
            },
            "recovery_guidance": [
                "Run `browser-cli reload` if cleanup failures continue to appear.",
            ],
            "available_actions": ["refresh-status"],
        },
    }
    with (
        patch("browser_cli.commands.status.get_app_paths", return_value=_fake_paths(tmp_path)),
        patch("browser_cli.commands.status.read_run_info", return_value=run_info),
        patch("browser_cli.commands.status.probe_socket", return_value=True),
        patch("browser_cli.commands.status.send_command", return_value={"ok": True, "data": runtime_status}),
    ):
        text = run_status_command(Namespace())

    assert "Stability" in text
    assert "commands started: 7" in text
    assert "cleanup failures: 2" in text
    assert "last cleanup error: No tab with id: 685338567." in text
```

- [ ] **Step 2: Run the presentation and status tests to verify they fail**

Run: `pytest tests/unit/test_runtime_presentation.py::test_build_runtime_presentation_marks_cleanup_failures_as_degraded tests/unit/test_lifecycle_commands.py::test_collect_status_report_renders_stability_section -q`
Expected: FAIL because presentation does not include `stability` and `status` does not render a stability section yet.

- [ ] **Step 3: Surface the stability snapshot in the shared truth path**

```python
def build_runtime_presentation(raw_status: dict[str, Any]) -> dict[str, Any]:
    browser_started = bool(raw_status.get("browser_started"))
    active_driver = str(raw_status.get("active_driver") or "not-started")
    pending_rebind = _as_dict_or_none(raw_status.get("pending_rebind"))
    extension = dict(raw_status.get("extension") or {})
    workspace_window_state = dict(raw_status.get("workspace_window_state") or {})
    tabs = dict(raw_status.get("tabs") or {})
    busy_tab_count = int(tabs.get("busy_count") or 0)
    binding_state = str(workspace_window_state.get("binding_state") or "absent")
    extension_connected = bool(extension.get("connected"))
    capability_complete = bool(extension.get("capability_complete"))
    stability = dict(raw_status.get("stability") or {})
    cleanup_failures = int(stability.get("cleanup_failures") or 0)
    last_cleanup_error = str(stability.get("last_cleanup_error") or "").strip() or None
    execution_path = {
        "active_driver": active_driver,
        "pending_rebind": pending_rebind,
        "safe_point_wait": pending_rebind is not None,
        "last_transition": _as_dict_or_none(raw_status.get("last_transition")),
    }
    workspace_state = {
        "window_id": workspace_window_state.get("window_id"),
        "tab_count": int(workspace_window_state.get("tab_count") or 0),
        "managed_tab_count": int(workspace_window_state.get("managed_tab_count") or 0),
        "binding_state": binding_state,
        "busy_tab_count": busy_tab_count,
    }
    overall_state = "healthy"
    summary_reason = "Browser CLI runtime is healthy."
    recovery_guidance = ["Browser CLI can continue normally."]
    if not browser_started:
        summary_reason = "Browser runtime is idle and will start on the next browser command."
        recovery_guidance = ["Run a browser command to initialize runtime state."]
    elif active_driver == "not-started":
        overall_state = "broken"
        summary_reason = "Browser runtime reports started but no active driver is selected."
        recovery_guidance = [
            "Refresh runtime status to confirm the state.",
            "Reload Browser CLI if the runtime remains driverless.",
        ]
    elif pending_rebind is not None:
        overall_state = "recovering"
        summary_reason = _pending_rebind_summary(pending_rebind)
        recovery_guidance = _pending_rebind_guidance(pending_rebind)
    elif active_driver != "extension":
        overall_state = "degraded"
        summary_reason = "Browser CLI is running on Playwright instead of extension mode."
        recovery_guidance = [
            "Agent can continue on the managed profile backend.",
            "Reconnect the extension if real Chrome mode should be restored.",
        ]
    elif not extension_connected or not capability_complete:
        overall_state = "degraded"
        summary_reason = "Extension is connected but its required capabilities are incomplete."
        recovery_guidance = [
            "Reconnect or reload the extension.",
            "Refresh runtime status after extension health changes.",
        ]
    elif cleanup_failures:
        overall_state = "degraded"
        summary_reason = "Browser CLI recorded recent cleanup failures during runtime transitions."
        recovery_guidance = [
            "Run `browser-cli reload` if cleanup failures continue to appear.",
            "Refresh runtime status after the reload finishes.",
        ]

    return {
        "overall_state": overall_state,
        "summary_reason": summary_reason,
        "execution_path": execution_path,
        "workspace_state": workspace_state,
        "stability": {
            **stability,
            "last_cleanup_error": last_cleanup_error,
        },
        "recovery_guidance": recovery_guidance,
        "available_actions": _available_actions(
            active_driver=active_driver,
            pending_rebind=pending_rebind,
            extension_connected=extension_connected,
            capability_complete=capability_complete,
            binding_state=binding_state,
        ),
    }
```

```python
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
    stability: dict[str, Any] = field(default_factory=dict)
    workflow_service: dict[str, Any] = field(default_factory=dict)
    live_error: str | None = None
```

```python
stability = dict((live_payload or {}).get("stability") or {})
return StatusReport(
    overall_status=overall_status,
    daemon_state=daemon_state,
    runtime=runtime_section,
    daemon=daemon_section,
    workflow_service=workflow_service_section,
    backend=backend_section,
    browser=browser_section,
    guidance=guidance,
    presentation=presentation,
    stability=stability,
    live_error=live_error,
)
```

```python
def render_status_report(report: StatusReport) -> str:
    summary_reason = report.presentation.get("summary_reason") or "-"
    available_actions = ", ".join(report.presentation.get("available_actions") or []) or "none"
    lines = [f"Status: {report.overall_status}", "", f"Summary: {summary_reason}", ""]
    lines.extend(
        [
            "Runtime",
            f"  home: {report.runtime['home']}",
            f"  socket: {report.runtime['socket']}",
            f"  run-info: {report.runtime['run_info']}",
            f"  daemon log: {report.runtime['daemon_log']}",
            "",
            "Backend",
            f"  active driver: {_display_value(report.backend['active_driver'])}",
            f"  pending rebind: {report.backend['pending_rebind']}",
            "",
            "Browser",
            f"  workspace window: {report.browser['workspace_window']}",
            f"  workspace tab count: {report.browser['tab_count']}",
            "",
            "Stability",
            f"  active command: {_display_value(report.stability.get('active_command'))}",
            f"  command depth: {_display_value(report.stability.get('command_depth'))}",
            f"  commands started: {_display_value(report.stability.get('commands_started'))}",
            f"  driver switches: {_display_value(report.stability.get('driver_switches'))}",
            f"  workspace rebuilds: {_display_value(report.stability.get('workspace_rebuilds'))}",
            f"  extension disconnects: {_display_value(report.stability.get('extension_disconnects'))}",
            f"  cleanup failures: {_display_value(report.stability.get('cleanup_failures'))}",
            f"  last cleanup error: {_display_value(report.stability.get('last_cleanup_error'))}",
            "",
            "Guidance",
        ]
    )
```

- [ ] **Step 4: Run the presentation and status tests to verify they pass**

Run: `pytest tests/unit/test_runtime_presentation.py::test_build_runtime_presentation_marks_cleanup_failures_as_degraded tests/unit/test_lifecycle_commands.py::test_collect_status_report_renders_stability_section -q`
Expected: PASS

- [ ] **Step 5: Commit the presentation/status task**

```bash
git add src/browser_cli/daemon/runtime_presentation.py src/browser_cli/commands/status.py tests/unit/test_runtime_presentation.py tests/unit/test_lifecycle_commands.py
git commit -m "feat: surface runtime stability status"
```

### Task 3: Add Loop-Oriented Unit Validation For Rebinds And Artifacts

**Files:**
- Modify: `tests/unit/test_daemon_browser_service.py`
- Modify: `tests/unit/test_extension_transport.py`

- [ ] **Step 1: Write the failing loop-oriented unit tests**

```python
def test_browser_service_rebind_loop_keeps_tab_state_bounded(
    _patched_browser_service: _FakeExtensionHub,
) -> None:
    async def _scenario() -> None:
        _patched_browser_service.connect()
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

        for _ in range(3):
            _patched_browser_service.disconnect()
            await service.begin_command("tabs")
            await service.end_command()

            _patched_browser_service.connect()
            await service.begin_command("tabs")
            await service.end_command()

        status = await service.runtime_status()
        assert status["tabs"]["count"] == 1
        assert status["stability"]["driver_switches"] >= 2
        assert status["stability"]["extension_disconnects"] >= 1
        assert status["pending_rebind"] is None

        await service.stop()

    asyncio.run(_scenario())
```

```python
def test_extension_session_disconnect_does_not_poison_next_artifact_request(
    monkeypatch, tmp_path: Path
) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / ".browser-cli-runtime"))
        monkeypatch.setenv(EXTENSION_PORT_ENV, str(_unused_port()))

        hub = ExtensionHub()
        await hub.ensure_started()
        app_paths = get_app_paths()

        async with websockets.connect(app_paths.extension_ws_url) as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "protocol_version": PROTOCOL_VERSION,
                        "extension_version": "0.1.0-test",
                        "browser_name": "Chrome",
                        "browser_version": "146",
                        "capabilities": sorted(REQUIRED_EXTENSION_CAPABILITIES),
                        "workspace_window_state": {"connected": True},
                        "extension_instance_id": "ext-test",
                    }
                )
            )
            session = await hub.wait_for_session(timeout_seconds=1.0)
            assert session is not None

            failing = asyncio.create_task(session.send_request("trace-stop", {}))
            raw_request = json.loads(await websocket.recv())
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-begin",
                        "request_id": raw_request["id"],
                        "artifact_id": "artifact-2",
                        "artifact_kind": "trace",
                        "mime_type": "application/zip",
                        "encoding": "base64",
                        "filename": "trace.zip",
                    }
                )
            )
            await websocket.close()
            with pytest.raises(OperationFailedError):
                await failing

        async with websockets.connect(app_paths.extension_ws_url) as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "protocol_version": PROTOCOL_VERSION,
                        "extension_version": "0.1.0-test",
                        "browser_name": "Chrome",
                        "browser_version": "146",
                        "capabilities": sorted(REQUIRED_EXTENSION_CAPABILITIES),
                        "workspace_window_state": {"connected": True},
                        "extension_instance_id": "ext-test",
                    }
                )
            )
            session = await hub.wait_for_session(timeout_seconds=1.0)
            assert session is not None

            passing = asyncio.create_task(session.send_request("screenshot", {"full_page": False}))
            raw_request = json.loads(await websocket.recv())
            request_id = raw_request["id"]
            await websocket.send(
                json.dumps(
                    {
                        "type": "response",
                        "id": request_id,
                        "ok": True,
                        "data": {"ack": True},
                    }
                )
            )
            content = base64.b64encode(b"image").decode("ascii")
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-begin",
                        "request_id": request_id,
                        "artifact_id": "artifact-3",
                        "artifact_kind": "screenshot",
                        "mime_type": "image/png",
                        "encoding": "base64",
                        "filename": "page.png",
                        "page_id": "page_0001",
                        "metadata": {"full_page": False},
                    }
                )
            )
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-chunk",
                        "request_id": request_id,
                        "artifact_id": "artifact-3",
                        "artifact_kind": "screenshot",
                        "mime_type": "image/png",
                        "encoding": "base64",
                        "index": 0,
                        "chunk": content,
                        "final": True,
                    }
                )
            )
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-end",
                        "request_id": request_id,
                        "artifact_id": "artifact-3",
                        "size_bytes": 5,
                    }
                )
            )

            response = await passing
            assert response["_artifacts"][0]["artifact_kind"] == "screenshot"
            assert session._artifact_buffers == {}
            assert session._completed_artifacts == {}

        await hub.stop()

    asyncio.run(_scenario())
```

- [ ] **Step 2: Run the loop-oriented unit tests to verify they fail**

Run: `pytest tests/unit/test_daemon_browser_service.py::test_browser_service_rebind_loop_keeps_tab_state_bounded tests/unit/test_extension_transport.py::test_extension_session_disconnect_does_not_poison_next_artifact_request -q`
Expected: FAIL because the new tests do not exist yet and the rebind loop is not locked by assertions.

- [ ] **Step 3: Add the loop-oriented unit test coverage**

```python
# tests/unit/test_daemon_browser_service.py
def test_browser_service_rebind_loop_keeps_tab_state_bounded(
    _patched_browser_service: _FakeExtensionHub,
) -> None:
    async def _scenario() -> None:
        _patched_browser_service.connect()
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

        for _ in range(3):
            _patched_browser_service.disconnect()
            await service.begin_command("tabs")
            await service.end_command()

            _patched_browser_service.connect()
            await service.begin_command("tabs")
            await service.end_command()

        status = await service.runtime_status()
        assert status["tabs"]["count"] == 1
        assert status["tabs"]["records"][0]["page_id"] == page["page_id"]
        assert status["stability"]["driver_switches"] >= 2
        assert status["stability"]["extension_disconnects"] >= 1
        assert status["pending_rebind"] is None

        await service.stop()

    asyncio.run(_scenario())
```

```python
# tests/unit/test_extension_transport.py
def test_extension_session_disconnect_does_not_poison_next_artifact_request(
    monkeypatch, tmp_path: Path
) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / ".browser-cli-runtime"))
        monkeypatch.setenv(EXTENSION_PORT_ENV, str(_unused_port()))

        hub = ExtensionHub()
        await hub.ensure_started()
        app_paths = get_app_paths()

        async with websockets.connect(app_paths.extension_ws_url) as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "protocol_version": PROTOCOL_VERSION,
                        "extension_version": "0.1.0-test",
                        "browser_name": "Chrome",
                        "browser_version": "146",
                        "capabilities": sorted(REQUIRED_EXTENSION_CAPABILITIES),
                        "workspace_window_state": {"connected": True},
                        "extension_instance_id": "ext-test",
                    }
                )
            )
            session = await hub.wait_for_session(timeout_seconds=1.0)
            assert session is not None

            failing = asyncio.create_task(session.send_request("trace-stop", {}))
            raw_request = json.loads(await websocket.recv())
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-begin",
                        "request_id": raw_request["id"],
                        "artifact_id": "artifact-2",
                        "artifact_kind": "trace",
                        "mime_type": "application/zip",
                        "encoding": "base64",
                        "filename": "trace.zip",
                    }
                )
            )
            await websocket.close()
            with pytest.raises(OperationFailedError):
                await failing

        async with websockets.connect(app_paths.extension_ws_url) as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "protocol_version": PROTOCOL_VERSION,
                        "extension_version": "0.1.0-test",
                        "browser_name": "Chrome",
                        "browser_version": "146",
                        "capabilities": sorted(REQUIRED_EXTENSION_CAPABILITIES),
                        "workspace_window_state": {"connected": True},
                        "extension_instance_id": "ext-test",
                    }
                )
            )
            session = await hub.wait_for_session(timeout_seconds=1.0)
            assert session is not None

            passing = asyncio.create_task(session.send_request("screenshot", {"full_page": False}))
            raw_request = json.loads(await websocket.recv())
            request_id = raw_request["id"]
            await websocket.send(
                json.dumps(
                    {
                        "type": "response",
                        "id": request_id,
                        "ok": True,
                        "data": {"ack": True},
                    }
                )
            )
            content = base64.b64encode(b"image").decode("ascii")
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-begin",
                        "request_id": request_id,
                        "artifact_id": "artifact-3",
                        "artifact_kind": "screenshot",
                        "mime_type": "image/png",
                        "encoding": "base64",
                        "filename": "page.png",
                        "page_id": "page_0001",
                        "metadata": {"full_page": False},
                    }
                )
            )
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-chunk",
                        "request_id": request_id,
                        "artifact_id": "artifact-3",
                        "artifact_kind": "screenshot",
                        "mime_type": "image/png",
                        "encoding": "base64",
                        "index": 0,
                        "chunk": content,
                        "final": True,
                    }
                )
            )
            await websocket.send(
                json.dumps(
                    {
                        "type": "artifact-end",
                        "request_id": request_id,
                        "artifact_id": "artifact-3",
                        "size_bytes": 5,
                    }
                )
            )
        response = await passing
        assert response["ack"] is True
        assert response["_artifacts"][0]["artifact_kind"] == "screenshot"
        assert session._artifact_buffers == {}
        assert session._completed_artifacts == {}

        await hub.stop()

    asyncio.run(_scenario())
```

- [ ] **Step 4: Run the loop-oriented unit tests to verify they pass**

Run: `pytest tests/unit/test_daemon_browser_service.py::test_browser_service_rebind_loop_keeps_tab_state_bounded tests/unit/test_extension_transport.py::test_extension_session_disconnect_does_not_poison_next_artifact_request -q`
Expected: PASS

- [ ] **Step 5: Commit the loop-oriented unit tests**

```bash
git add tests/unit/test_daemon_browser_service.py tests/unit/test_extension_transport.py
git commit -m "test: add long-run runtime unit loops"
```

### Task 4: Add A Fixture-Backed Daemon Residency Integration Loop

**Files:**
- Create: `tests/integration/test_runtime_stability.py`

- [ ] **Step 1: Write the failing daemon residency integration test**

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from browser_cli.cli.main import main
from tests.integration.fixture_server import run_fixture_server
from tests.integration.test_daemon_actions import (
    _can_launch_daemon_browser,
    _configure_runtime,
    _run_cli_json,
    _run_cli_text,
    _stop_daemon,
)


@pytest.mark.integration
@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_daemon_residency_loop_keeps_runtime_status_consistent(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    with run_fixture_server() as base_url:
        _configure_runtime(monkeypatch, tmp_path)

        for round_index in range(3):
            open_payload = _run_cli_json(["open", f"{base_url}/interactive"], capsys)
            assert open_payload["meta"]["driver"] in {"playwright", "extension"}

            status_text = _run_cli_text(["status"], capsys)
            assert "Status:" in status_text
            assert "broken" not in status_text.lower()

            snapshot_payload = _run_cli_json(["snapshot"], capsys)
            assert snapshot_payload["data"]["refs_summary"]

            html_payload = _run_cli_json(["html"], capsys)
            assert "<html" in html_payload["data"]["html"].lower()

            close_payload = _run_cli_json(["close"], capsys)
            assert close_payload["data"]["closed"] is True

            if round_index == 1:
                reload_text = _run_cli_text(["reload"], capsys)
                assert "Reload: complete" in reload_text

        final_status = _run_cli_text(["status"], capsys)
        assert "Status: broken" not in final_status
        _stop_daemon(capsys)
```

- [ ] **Step 2: Run the daemon residency integration test to verify it fails**

Run: `pytest tests/integration/test_runtime_stability.py::test_daemon_residency_loop_keeps_runtime_status_consistent -q`
Expected: FAIL because the file does not exist yet.

- [ ] **Step 3: Add the integration loop file**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.fixture_server import run_fixture_server
from tests.integration.test_daemon_actions import (
    _can_launch_daemon_browser,
    _configure_runtime,
    _run_cli_json,
    _run_cli_text,
    _stop_daemon,
)


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_daemon_residency_loop_keeps_runtime_status_consistent(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    with run_fixture_server() as base_url:
        _configure_runtime(monkeypatch, tmp_path)

        for round_index in range(3):
            open_payload = _run_cli_json(["open", f"{base_url}/interactive"], capsys)
            assert open_payload["meta"]["driver"] in {"playwright", "extension"}

            status_text = _run_cli_text(["status"], capsys)
            assert "Status:" in status_text
            assert "Status: broken" not in status_text

            snapshot_payload = _run_cli_json(["snapshot"], capsys)
            assert snapshot_payload["data"]["refs_summary"]

            html_payload = _run_cli_json(["html"], capsys)
            assert "<html" in html_payload["data"]["html"].lower()

            close_payload = _run_cli_json(["close"], capsys)
            assert close_payload["data"]["closed"] is True

            if round_index == 1:
                reload_text = _run_cli_text(["reload"], capsys)
                assert "Reload: complete" in reload_text

        final_status = _run_cli_text(["status"], capsys)
        assert "Status: broken" not in final_status
        _stop_daemon(capsys)
```

- [ ] **Step 4: Run the daemon residency integration test to verify it passes**

Run: `pytest tests/integration/test_runtime_stability.py::test_daemon_residency_loop_keeps_runtime_status_consistent -q`
Expected: PASS on machines that can launch the daemon browser; `SKIPPED` is acceptable on machines without stable Chrome runtime.

- [ ] **Step 5: Commit the daemon residency integration loop**

```bash
git add tests/integration/test_runtime_stability.py
git commit -m "test: add daemon residency stability loop"
```

### Task 5: Document Long-Run Smoke And Agent Triage

**Files:**
- Modify: `docs/smoke-checklist.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Write the failing doc assertions by searching for the new long-run guidance**

Run: `rg -n "Long-Run Runtime Checks|stability counters|status/popup drift" docs/smoke-checklist.md AGENTS.md`
Expected: no matches

- [ ] **Step 2: Update the smoke checklist with long-run runtime checks**

```md
## Long-Run Runtime Checks

- Start Browser CLI and keep the same daemon alive for at least three rounds of `open`, `snapshot`, `html`, `close`.
- Run `browser-cli status` between rounds and confirm the `Stability` section reports bounded counts plus a non-growing `command depth`.
- Run `browser-cli reload` mid-way, then confirm the next `browser-cli status` still reports a usable runtime instead of a wedged degraded state.
- If extension mode is available, disconnect and reconnect it during the loop and confirm `status`, popup, and command `meta` agree on the active driver and any `state_reset`.
- Exercise one artifact round after a disconnect/reconnect cycle and confirm the next artifact still succeeds without stale buffers poisoning the session.
```

- [ ] **Step 3: Update AGENTS.md with the recurring long-run stability triage path**

```md
- If the user reports long-run stability drift, start at `src/browser_cli/daemon/browser_service.py`, `src/browser_cli/daemon/runtime_presentation.py`, `src/browser_cli/commands/status.py`, and `src/browser_cli/extension/session.py`.
- Typical symptom -> root cause -> where to inspect:
  `status` / popup / command `meta` disagree after repeated reconnect or reload
  -> runtime truth path drift
  -> inspect `browser_service.runtime_status`, `runtime_presentation.build_runtime_presentation`, `commands/status.py`, and popup-facing extension status endpoints.
- If repeated artifact failures poison later requests, inspect extension artifact buffering and disconnect cleanup in `src/browser_cli/extension/session.py` plus `tests/unit/test_extension_transport.py`.
```

- [ ] **Step 4: Run the focused doc-and-test verification**

Run: `pytest tests/unit/test_daemon_browser_service.py::test_browser_service_runtime_status_tracks_stability_metrics tests/unit/test_runtime_presentation.py::test_build_runtime_presentation_marks_cleanup_failures_as_degraded tests/unit/test_lifecycle_commands.py::test_collect_status_report_renders_stability_section tests/unit/test_extension_transport.py::test_extension_session_disconnect_does_not_poison_next_artifact_request -q && scripts/check.sh`
Expected: targeted tests PASS; `scripts/check.sh` ends with `All checks passed!`

- [ ] **Step 5: Commit the docs and final verification task**

```bash
git add docs/smoke-checklist.md AGENTS.md docs/superpowers/plans/2026-04-13-browser-cli-long-run-stability-implementation-plan.md
git commit -m "docs: add long-run runtime stability guidance"
```
