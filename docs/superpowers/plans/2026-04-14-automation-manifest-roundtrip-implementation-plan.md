# Automation Manifest Round-Trip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify Browser CLI automation manifest semantics across publish, import, export, inspect, and persistence so supported fields round-trip without silent drift.

**Architecture:** Add a shared automation projection layer under `src/browser_cli/automation/projections.py` and route manifest-to-persistence, persistence-to-manifest, snapshot-manifest rendering, and inspect config payload generation through it. Keep `AutomationManifest` and `PersistedAutomationDefinition` as the durable semantic models, but make publisher, API, and inspect surfaces delegate field projection to one shared implementation.

**Tech Stack:** Python 3.10, pytest, Browser CLI automation loader/publisher/API modules, `dumps_toml_sections`

---

## File Map

- Create: `src/browser_cli/automation/projections.py`
  Responsibility: shared semantic projections among manifest, persisted definition, API payloads, snapshot manifests, and inspect config views.
- Create: `tests/unit/test_automation_projections.py`
  Responsibility: round-trip regression tests for semantic field preservation and inspect config parity.
- Modify: `src/browser_cli/automation/models.py`
  Responsibility: retain dataclasses and convert the existing manifest-to-persisted helper into a compatibility wrapper over the new projection layer.
- Modify: `src/browser_cli/automation/persistence/store.py`
  Responsibility: persist the shared supported field set, including `runtime.log_level`, through sqlite storage and reload.
- Modify: `src/browser_cli/automation/publisher.py`
  Responsibility: replace local snapshot-manifest assembly with shared projection helpers.
- Modify: `src/browser_cli/automation/api/server.py`
  Responsibility: replace local payload conversion, export TOML rendering, and automation serialization with shared projection helpers.
- Modify: `src/browser_cli/commands/automation.py`
  Responsibility: build `snapshot_config` and `live_config` from the same shared config-view projection.
- Modify: `tests/unit/test_task_runtime_automation.py`
  Responsibility: keep existing manifest-to-persisted assertions pointed at the shared projection behavior.
- Modify: `tests/unit/test_automation_publish.py`
  Responsibility: assert published snapshot manifests preserve the full supported field set after path remapping.
- Modify: `tests/unit/test_automation_api.py`
  Responsibility: assert export TOML round-trips supported fields semantically.
- Modify: `tests/unit/test_automation_commands.py`
  Responsibility: assert `inspect --version` renders `snapshot_config` and `live_config` with the same supported config field shape.
- Modify: `docs/superpowers/plans/2026-04-14-automation-manifest-roundtrip-implementation-plan.md`
  Responsibility: mark task completion during execution if this plan is used as the working log.

## Task 1: Add Failing Semantic Round-Trip Regression Tests

**Files:**
- Create: `tests/unit/test_automation_projections.py`
- Test: `tests/unit/test_automation_projections.py`

- [x] **Step 1: Write failing projection regression tests**

Create `tests/unit/test_automation_projections.py`:

```python
from __future__ import annotations

from pathlib import Path

from browser_cli.automation.loader import load_automation_manifest
from browser_cli.automation.models import PersistedAutomationDefinition
from browser_cli.automation.projections import (
    manifest_to_config_payload,
    manifest_to_persisted_definition,
    manifest_to_snapshot_manifest_toml,
    persisted_definition_to_config_payload,
    persisted_definition_to_manifest_toml,
)


def _write_task_fixture(base_dir: Path) -> Path:
    task_dir = base_dir / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    (task_dir / "automation.toml").write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo"\n'
        'description = "Semantic round-trip"\n'
        'version = "7"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n'
        'entrypoint = "run"\n'
        "[inputs]\n"
        'url = "https://example.com"\n'
        "[schedule]\n"
        'mode = "interval"\n'
        "interval_seconds = 900\n"
        'timezone = "Asia/Shanghai"\n'
        "[outputs]\n"
        'artifact_dir = "artifacts"\n'
        'result_json_path = "artifacts/result.json"\n'
        'stdout = "text"\n'
        "[hooks]\n"
        'before_run = ["echo before"]\n'
        'after_success = ["echo success"]\n'
        'after_failure = ["echo failure"]\n'
        "[runtime]\n"
        "retry_attempts = 2\n"
        "retry_backoff_seconds = 11\n"
        "timeout_seconds = 42.5\n"
        'log_level = "debug"\n',
        encoding="utf-8",
    )
    return task_dir


def _build_persisted_definition(base_dir: Path) -> PersistedAutomationDefinition:
    return PersistedAutomationDefinition(
        id="demo",
        name="Demo",
        description="Semantic round-trip",
        version="7",
        task_path=base_dir / "live" / "task.py",
        task_meta_path=base_dir / "live" / "task.meta.json",
        entrypoint="run",
        enabled=True,
        schedule_kind="interval",
        schedule_payload={
            "mode": "interval",
            "interval_seconds": 900,
            "timezone": "Asia/Shanghai",
        },
        timezone="Asia/Shanghai",
        output_dir=base_dir / "runs",
        result_json_path=base_dir / "runs" / "result.json",
        stdout_mode="text",
        input_overrides={"url": "https://example.com"},
        before_run_hooks=("echo before",),
        after_success_hooks=("echo success",),
        after_failure_hooks=("echo failure",),
        retry_attempts=2,
        retry_backoff_seconds=11,
        timeout_seconds=42.5,
        log_level="debug",
    )


def test_manifest_to_persisted_definition_preserves_supported_fields(tmp_path: Path) -> None:
    manifest = load_automation_manifest(_write_task_fixture(tmp_path) / "automation.toml")

    persisted = manifest_to_persisted_definition(manifest, enabled=True)

    assert persisted.description == "Semantic round-trip"
    assert persisted.schedule_kind == "interval"
    assert persisted.schedule_payload["interval_seconds"] == 900
    assert persisted.timezone == "Asia/Shanghai"
    assert persisted.result_json_path is not None
    assert persisted.stdout_mode == "text"
    assert persisted.before_run_hooks == ("echo before",)
    assert persisted.after_success_hooks == ("echo success",)
    assert persisted.after_failure_hooks == ("echo failure",)
    assert persisted.retry_attempts == 2
    assert persisted.retry_backoff_seconds == 11
    assert persisted.timeout_seconds == 42.5


def test_persisted_definition_to_manifest_toml_round_trips_supported_fields(
    tmp_path: Path,
) -> None:
    automation = _build_persisted_definition(tmp_path)
    automation.task_path.parent.mkdir(parents=True)
    automation.task_path.write_text("def run(flow, inputs):\n    return {}\n", encoding="utf-8")
    automation.task_meta_path.write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )

    manifest_path = tmp_path / "exported.toml"
    manifest_path.write_text(
        persisted_definition_to_manifest_toml(automation),
        encoding="utf-8",
    )

    manifest = load_automation_manifest(manifest_path)

    assert manifest.inputs == {"url": "https://example.com"}
    assert manifest.schedule["interval_seconds"] == 900
    assert manifest.schedule["timezone"] == "Asia/Shanghai"
    assert manifest.outputs.stdout == "text"
    assert manifest.hooks.after_failure == ("echo failure",)
    assert manifest.runtime.retry_backoff_seconds == 11
    assert manifest.runtime.timeout_seconds == 42.5
    assert manifest.runtime.log_level == "debug"


def test_manifest_to_snapshot_manifest_toml_remaps_paths_without_losing_supported_fields(
    tmp_path: Path,
) -> None:
    task_dir = _write_task_fixture(tmp_path)
    manifest = load_automation_manifest(task_dir / "automation.toml")
    snapshot_dir = tmp_path / "home" / "automations" / "demo" / "versions" / "3"
    snapshot_dir.mkdir(parents=True)
    task_path = snapshot_dir / "task.py"
    task_meta_path = snapshot_dir / "task.meta.json"
    task_path.write_text("def run(flow, inputs):\n    return {}\n", encoding="utf-8")
    task_meta_path.write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )

    manifest_path = snapshot_dir / "automation.toml"
    manifest_path.write_text(
        manifest_to_snapshot_manifest_toml(
            manifest,
            version=3,
            task_path=task_path,
            task_meta_path=task_meta_path,
            output_dir=tmp_path / "home" / "automations" / "demo",
        ),
        encoding="utf-8",
    )

    snapshot_manifest = load_automation_manifest(manifest_path)

    assert snapshot_manifest.automation.version == "3"
    assert snapshot_manifest.task.path == task_path
    assert snapshot_manifest.task.meta_path == task_meta_path
    assert snapshot_manifest.outputs.result_json_path is not None
    assert snapshot_manifest.outputs.result_json_path.name == "result.json"
    assert snapshot_manifest.hooks.after_success == ("echo success",)
    assert snapshot_manifest.runtime.log_level == "debug"


def test_manifest_and_persisted_config_payloads_share_supported_keys(tmp_path: Path) -> None:
    manifest = load_automation_manifest(_write_task_fixture(tmp_path) / "automation.toml")
    persisted = _build_persisted_definition(tmp_path)

    manifest_payload = manifest_to_config_payload(manifest)
    persisted_payload = persisted_definition_to_config_payload(persisted)

    assert set(manifest_payload) == set(persisted_payload)
    assert manifest_payload["timezone"] == "Asia/Shanghai"
    assert persisted_payload["timezone"] == "Asia/Shanghai"
    assert manifest_payload["retry_backoff_seconds"] == 11
    assert persisted_payload["retry_backoff_seconds"] == 11
    assert manifest_payload["log_level"] == "debug"
    assert persisted_payload["log_level"] == "debug"
```

- [ ] **Step 2: Run the new regression suite and verify it fails**

Run:

```bash
uv run pytest tests/unit/test_automation_projections.py -v
```

Expected: FAIL because `browser_cli.automation.projections` does not exist yet and the shared projection helpers are not implemented.

- [ ] **Step 3: Commit the failing regression scaffold**

```bash
git add tests/unit/test_automation_projections.py
git commit -m "test: add automation projection round-trip regressions"
```

## Task 2: Implement The Shared Projection Layer

**Files:**
- Create: `src/browser_cli/automation/projections.py`
- Modify: `src/browser_cli/automation/models.py`
- Modify: `tests/unit/test_task_runtime_automation.py`
- Test: `tests/unit/test_automation_projections.py`
- Test: `tests/unit/test_task_runtime_automation.py`

- [x] **Step 1: Implement shared projection helpers**

Create `src/browser_cli/automation/projections.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from browser_cli.automation.models import (
    AutomationManifest,
    PersistedAutomationDefinition,
)
from browser_cli.automation.toml import dumps_toml_sections


def manifest_to_persisted_definition(
    manifest: AutomationManifest,
    *,
    enabled: bool = False,
) -> PersistedAutomationDefinition:
    return PersistedAutomationDefinition(
        id=manifest.automation.id,
        name=manifest.automation.name,
        description=manifest.automation.description,
        version=str(manifest.automation.version),
        task_path=manifest.task.path,
        task_meta_path=manifest.task.meta_path,
        entrypoint=manifest.task.entrypoint,
        enabled=enabled,
        schedule_kind=str(manifest.schedule.get("mode") or "manual"),
        schedule_payload=dict(manifest.schedule),
        timezone=str(manifest.schedule.get("timezone") or "UTC"),
        output_dir=manifest.outputs.artifact_dir,
        result_json_path=manifest.outputs.result_json_path,
        stdout_mode=manifest.outputs.stdout,
        input_overrides=dict(manifest.inputs),
        before_run_hooks=manifest.hooks.before_run,
        after_success_hooks=manifest.hooks.after_success,
        after_failure_hooks=manifest.hooks.after_failure,
        retry_attempts=manifest.runtime.retry_attempts,
        retry_backoff_seconds=manifest.runtime.retry_backoff_seconds,
        timeout_seconds=manifest.runtime.timeout_seconds,
        log_level=manifest.runtime.log_level,
    )


def payload_to_persisted_definition(payload: dict[str, Any]) -> PersistedAutomationDefinition:
    automation_id = str(payload.get("id") or "").strip()
    output_dir_raw = str(payload.get("output_dir") or "").strip()
    result_json_raw = str(payload.get("result_json_path") or "").strip()
    return PersistedAutomationDefinition(
        id=automation_id,
        name=str(payload.get("name") or automation_id),
        description=str(payload.get("description") or ""),
        version=str(payload.get("version") or "0.1.0"),
        task_path=Path(str(payload.get("task_path") or "")),
        task_meta_path=Path(str(payload.get("task_meta_path") or "")),
        entrypoint=str(payload.get("entrypoint") or "run"),
        enabled=bool(payload.get("enabled")),
        definition_status=str(payload.get("definition_status") or "valid"),
        definition_error=str(payload.get("definition_error")) if payload.get("definition_error") else None,
        schedule_kind=str(payload.get("schedule_kind") or "manual"),
        schedule_payload=dict(payload.get("schedule_payload") or {}),
        timezone=str(payload.get("timezone") or "UTC"),
        output_dir=Path(output_dir_raw) if output_dir_raw else Path(),
        result_json_path=Path(result_json_raw) if result_json_raw else None,
        stdout_mode=str(payload.get("stdout_mode") or "json"),
        input_overrides=dict(payload.get("input_overrides") or {}),
        before_run_hooks=tuple(payload.get("before_run_hooks") or []),
        after_success_hooks=tuple(payload.get("after_success_hooks") or []),
        after_failure_hooks=tuple(payload.get("after_failure_hooks") or []),
        retry_attempts=int(payload.get("retry_attempts") or 0),
        retry_backoff_seconds=int(payload.get("retry_backoff_seconds") or 0),
        timeout_seconds=float(payload["timeout_seconds"]) if payload.get("timeout_seconds") is not None else None,
        log_level=str(payload.get("log_level") or "info"),
    )


def persisted_definition_to_manifest_toml(
    automation: PersistedAutomationDefinition,
) -> str:
    return dumps_toml_sections(
        [
            ("automation", {
                "id": automation.id,
                "name": automation.name,
                "description": automation.description,
                "version": automation.version,
            }),
            ("task", {
                "path": str(automation.task_path),
                "meta_path": str(automation.task_meta_path),
                "entrypoint": automation.entrypoint,
            }),
            ("inputs", dict(automation.input_overrides)),
            ("schedule", _schedule_values(automation)),
            ("outputs", {
                "artifact_dir": str(automation.output_dir),
                "result_json_path": str(automation.result_json_path) if automation.result_json_path else None,
                "stdout": automation.stdout_mode,
            }),
            ("hooks", {
                "before_run": list(automation.before_run_hooks),
                "after_success": list(automation.after_success_hooks),
                "after_failure": list(automation.after_failure_hooks),
            }),
            ("runtime", {
                "retry_attempts": automation.retry_attempts,
                "retry_backoff_seconds": automation.retry_backoff_seconds,
                "timeout_seconds": automation.timeout_seconds,
                "log_level": automation.log_level,
            }),
        ]
    )


def manifest_to_snapshot_manifest_toml(
    manifest: AutomationManifest,
    *,
    version: int,
    task_path: Path,
    task_meta_path: Path,
    output_dir: Path,
) -> str:
    result_json_path = _remap_result_json_path(
        manifest.outputs.artifact_dir,
        manifest.outputs.result_json_path,
        output_dir,
    )
    return dumps_toml_sections(
        [
            ("automation", {
                "id": manifest.automation.id,
                "name": manifest.automation.name,
                "description": manifest.automation.description,
                "version": str(version),
            }),
            ("task", {
                "path": str(task_path),
                "meta_path": str(task_meta_path),
                "entrypoint": manifest.task.entrypoint,
            }),
            ("inputs", dict(manifest.inputs)),
            ("schedule", dict(manifest.schedule)),
            ("outputs", {
                "artifact_dir": str(output_dir),
                "result_json_path": str(result_json_path) if result_json_path else None,
                "stdout": manifest.outputs.stdout,
            }),
            ("hooks", {
                "before_run": list(manifest.hooks.before_run),
                "after_success": list(manifest.hooks.after_success),
                "after_failure": list(manifest.hooks.after_failure),
            }),
            ("runtime", {
                "retry_attempts": manifest.runtime.retry_attempts,
                "retry_backoff_seconds": manifest.runtime.retry_backoff_seconds,
                "timeout_seconds": manifest.runtime.timeout_seconds,
                "log_level": manifest.runtime.log_level,
            }),
        ]
    )


def manifest_to_config_payload(manifest: AutomationManifest) -> dict[str, object]:
    return {
        "id": manifest.automation.id,
        "name": manifest.automation.name,
        "description": manifest.automation.description,
        "version": str(manifest.automation.version),
        "task_path": str(manifest.task.path),
        "task_meta_path": str(manifest.task.meta_path),
        "entrypoint": manifest.task.entrypoint,
        "schedule_kind": str(manifest.schedule.get("mode") or "manual"),
        "schedule_payload": dict(manifest.schedule),
        "timezone": str(manifest.schedule.get("timezone") or "UTC"),
        "output_dir": str(manifest.outputs.artifact_dir),
        "result_json_path": str(manifest.outputs.result_json_path) if manifest.outputs.result_json_path else None,
        "stdout_mode": manifest.outputs.stdout,
        "input_overrides": dict(manifest.inputs),
        "before_run_hooks": list(manifest.hooks.before_run),
        "after_success_hooks": list(manifest.hooks.after_success),
        "after_failure_hooks": list(manifest.hooks.after_failure),
        "retry_attempts": manifest.runtime.retry_attempts,
        "retry_backoff_seconds": manifest.runtime.retry_backoff_seconds,
        "timeout_seconds": manifest.runtime.timeout_seconds,
        "log_level": manifest.runtime.log_level,
    }


def persisted_definition_to_config_payload(
    automation: PersistedAutomationDefinition,
) -> dict[str, object]:
    return {
        "id": automation.id,
        "name": automation.name,
        "description": automation.description,
        "version": automation.version,
        "task_path": str(automation.task_path),
        "task_meta_path": str(automation.task_meta_path),
        "entrypoint": automation.entrypoint,
        "schedule_kind": automation.schedule_kind,
        "schedule_payload": dict(automation.schedule_payload),
        "timezone": automation.timezone,
        "output_dir": str(automation.output_dir),
        "result_json_path": str(automation.result_json_path) if automation.result_json_path else None,
        "stdout_mode": automation.stdout_mode,
        "input_overrides": dict(automation.input_overrides),
        "before_run_hooks": list(automation.before_run_hooks),
        "after_success_hooks": list(automation.after_success_hooks),
        "after_failure_hooks": list(automation.after_failure_hooks),
        "retry_attempts": automation.retry_attempts,
        "retry_backoff_seconds": automation.retry_backoff_seconds,
        "timeout_seconds": automation.timeout_seconds,
        "log_level": automation.log_level,
    }


def _schedule_values(automation: PersistedAutomationDefinition) -> dict[str, Any]:
    values = {"mode": automation.schedule_kind, "timezone": automation.timezone}
    for key, value in automation.schedule_payload.items():
        if key not in {"mode", "timezone"}:
            values[key] = value
    return values


def _remap_result_json_path(
    source_artifact_dir: Path,
    source_result_json_path: Path | None,
    target_artifact_dir: Path,
) -> Path | None:
    if source_result_json_path is None:
        return None
    try:
        relative = source_result_json_path.relative_to(source_artifact_dir)
    except ValueError:
        return target_artifact_dir / source_result_json_path.name
    return target_artifact_dir / relative
```

- [x] **Step 2: Convert `models.py` into a compatibility wrapper**

Update `src/browser_cli/automation/models.py`:

```python
    log_level: str = "info"

def manifest_to_persisted_definition(
    manifest: AutomationManifest,
    *,
    enabled: bool = False,
) -> PersistedAutomationDefinition:
    from browser_cli.automation.projections import manifest_to_persisted_definition as _impl

    return _impl(manifest, enabled=enabled)
```

- [x] **Step 3: Point the existing manifest regression test at the shared behavior**

Update `tests/unit/test_task_runtime_automation.py`:

```python
from browser_cli.automation.projections import manifest_to_persisted_definition
```

Keep the existing assertion body intact so the old retry-backoff/timeout check
continues covering the new projection module, and append:

```python
    assert persisted.log_level == "info"
```

- [x] **Step 4: Run the focused projection suites**

Run:

```bash
uv run pytest tests/unit/test_automation_projections.py tests/unit/test_task_runtime_automation.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/browser_cli/automation/projections.py src/browser_cli/automation/models.py tests/unit/test_automation_projections.py tests/unit/test_task_runtime_automation.py
git commit -m "refactor: add shared automation projections"
```

## Task 3: Route Publish And API Export Through Shared Projections

**Files:**
- Modify: `src/browser_cli/automation/persistence/store.py`
- Modify: `src/browser_cli/automation/publisher.py`
- Modify: `src/browser_cli/automation/api/server.py`
- Modify: `tests/unit/test_automation_publish.py`
- Modify: `tests/unit/test_automation_api.py`
- Test: `tests/unit/test_automation_publish.py`
- Test: `tests/unit/test_automation_api.py`

- [x] **Step 1: Add failing publish and export regressions for the remaining supported fields**

Append to `tests/unit/test_automation_publish.py`:

```python
def test_publish_task_dir_preserves_hooks_timeout_and_log_level(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    (task_dir / "automation.toml").write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n'
        "[hooks]\n"
        'before_run = [\"echo before\"]\n'
        'after_success = [\"echo success\"]\n'
        'after_failure = [\"echo failure\"]\n'
        "[runtime]\n"
        "timeout_seconds = 6.5\n"
        'log_level = "debug"\n',
        encoding="utf-8",
    )

    published = publish_task_dir(task_dir, app_paths=get_app_paths())
    manifest = load_automation_manifest(published.manifest_path)

    assert manifest.hooks.before_run == ("echo before",)
    assert manifest.hooks.after_success == ("echo success",)
    assert manifest.hooks.after_failure == ("echo failure",)
    assert manifest.runtime.timeout_seconds == 6.5
    assert manifest.runtime.log_level == "debug"
```

Append to `tests/unit/test_automation_api.py`:

```python
def test_automation_api_export_round_trips_supported_fields(tmp_path: Path) -> None:
    runtime = AutomationServiceRuntime(store=AutomationStore(tmp_path / "automations.db"))
    server = AutomationHttpServer(("127.0.0.1", 0), AutomationRequestHandler, runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        create_payload = _request(
            host,
            int(port),
            "POST",
            "/api/automations",
            {
                "id": "demo",
                "name": "Demo",
                "description": "Round trip",
                "version": "7",
                "task_path": str(tmp_path / "task.py"),
                "task_meta_path": str(tmp_path / "task.meta.json"),
                "entrypoint": "run",
                "schedule_kind": "interval",
                "schedule_payload": {
                    "mode": "interval",
                    "interval_seconds": 900,
                    "timezone": "Asia/Shanghai",
                },
                "timezone": "Asia/Shanghai",
                "output_dir": str(tmp_path / "runs"),
                "result_json_path": str(tmp_path / "runs" / "result.json"),
                "stdout_mode": "text",
                "input_overrides": {"url": "https://example.com"},
                "before_run_hooks": ["echo before"],
                "after_success_hooks": ["echo success"],
                "after_failure_hooks": ["echo failure"],
                "retry_attempts": 2,
                "retry_backoff_seconds": 11,
                "timeout_seconds": 42.5,
                "log_level": "debug",
            },
        )
        assert create_payload["data"]["id"] == "demo"

        export_payload = _request(host, int(port), "GET", "/api/automations/demo/export")
        manifest_path = tmp_path / "exported.toml"
        manifest_path.write_text(export_payload["data"]["toml"], encoding="utf-8")
        (tmp_path / "task.py").write_text(
            "def run(flow, inputs):\n    return {'ok': True}\n",
            encoding="utf-8",
        )
        (tmp_path / "task.meta.json").write_text(
            '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
            encoding="utf-8",
        )
        manifest = load_automation_manifest(manifest_path)

        assert manifest.inputs == {"url": "https://example.com"}
        assert manifest.schedule["interval_seconds"] == 900
        assert manifest.outputs.stdout == "text"
        assert manifest.hooks.after_success == ("echo success",)
        assert manifest.runtime.retry_backoff_seconds == 11
        assert manifest.runtime.timeout_seconds == 42.5
        assert manifest.runtime.log_level == "debug"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
```

Run:

```bash
uv run pytest tests/unit/test_automation_publish.py tests/unit/test_automation_api.py -v
```

Expected: FAIL because publish and export still use local assembly code paths that do not share the new projection layer.

- [x] **Step 2: Refactor publish and API export/import serialization**

Update `src/browser_cli/automation/publisher.py`:

```python
from browser_cli.automation.projections import manifest_to_snapshot_manifest_toml

    if source_manifest_path.exists():
        manifest_source = "task_dir"
        source_manifest = load_automation_manifest(source_manifest_path)
        rendered_manifest = manifest_to_snapshot_manifest_toml(
            source_manifest,
            version=version,
            task_path=task_path,
            task_meta_path=task_meta_path,
            output_dir=automation_root,
        )
```

Update `src/browser_cli/automation/api/server.py`:

```python
from browser_cli.automation.projections import (
    manifest_to_persisted_definition,
    payload_to_persisted_definition,
    persisted_definition_to_config_payload,
    persisted_definition_to_manifest_toml,
)
```

Replace the direct payload conversion and export helpers:

```python
created = self.server.runtime.store.upsert_automation(payload_to_persisted_definition(body))
```

```python
automation = manifest_to_persisted_definition(manifest, enabled=enabled)
```

```python
self._send_json(
    {"ok": True, "data": {"toml": persisted_definition_to_manifest_toml(automation)}, "meta": {}}
)
```

And update `_serialize_automation()` so config fields come from the shared
projection helper first:

```python
payload = persisted_definition_to_config_payload(automation)
payload.update(
    {
        "enabled": automation.enabled,
        "definition_status": automation.definition_status,
        "definition_error": automation.definition_error,
        "created_at": automation.created_at,
        "updated_at": automation.updated_at,
        "last_run_at": automation.last_run_at,
        "next_run_at": automation.next_run_at,
    }
)
```

Update `src/browser_cli/automation/persistence/store.py` so sqlite preserves the
new supported field:

```python
                CREATE TABLE IF NOT EXISTS automations (
                    ...
                    retry_backoff_seconds INTEGER NOT NULL DEFAULT 0,
                    timeout_seconds REAL,
                    log_level TEXT NOT NULL DEFAULT 'info',
                    created_at TEXT NOT NULL,
                    ...
                );
```

Add a lightweight additive migration in `_initialize()`:

```python
            self._ensure_column(
                conn,
                "automations",
                "log_level",
                "TEXT NOT NULL DEFAULT 'info'",
            )
```

Add the helper on `AutomationStore`:

```python
    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        ddl: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
```

Update the `INSERT` / `ON CONFLICT` statement field lists to include
`log_level`:

```python
                    after_failure_hooks_json, retry_attempts, retry_backoff_seconds,
                    timeout_seconds, log_level, created_at, updated_at, last_run_at, next_run_at
```

```python
                    retry_backoff_seconds = excluded.retry_backoff_seconds,
                    timeout_seconds = excluded.timeout_seconds,
                    log_level = excluded.log_level,
                    updated_at = excluded.updated_at,
```

And wire the row conversion helpers:

```python
        "log_level": automation.log_level,
```

```python
        log_level=str(row["log_level"] or "info"),
```

Delete `_automation_to_toml()` and `_payload_to_automation()` after routing all
callers through the shared projection layer.

- [x] **Step 3: Run the focused publish and API suites**

Run:

```bash
uv run pytest tests/unit/test_automation_publish.py tests/unit/test_automation_api.py -v
```

Expected: PASS

- [x] **Step 4: Commit**

```bash
git add src/browser_cli/automation/publisher.py src/browser_cli/automation/api/server.py tests/unit/test_automation_publish.py tests/unit/test_automation_api.py
git commit -m "refactor: route automation publish and export through projections"
```

## Task 4: Align Inspect Snapshot And Live Config Views

**Files:**
- Modify: `src/browser_cli/commands/automation.py`
- Modify: `tests/unit/test_automation_commands.py`
- Test: `tests/unit/test_automation_commands.py`

- [x] **Step 1: Add a failing inspect parity regression**

Append to `tests/unit/test_automation_commands.py`:

```python
def test_automation_inspect_version_aligns_snapshot_and_live_config_shapes(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    version_dir = tmp_path / "home" / "automations" / "demo" / "versions" / "1"
    version_dir.mkdir(parents=True)
    (version_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    (version_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    (version_dir / "automation.toml").write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo Snapshot"\n'
        'description = "Snapshot"\n'
        'version = "1"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n'
        "[schedule]\n"
        'mode = "interval"\n'
        "interval_seconds = 900\n"
        'timezone = "Asia/Shanghai"\n'
        "[outputs]\n"
        'artifact_dir = "artifacts"\n'
        'result_json_path = "artifacts/result.json"\n'
        'stdout = "text"\n'
        "[hooks]\n"
        'before_run = [\"echo before\"]\n'
        'after_success = [\"echo success\"]\n'
        'after_failure = [\"echo failure\"]\n'
        "[runtime]\n"
        "retry_attempts = 2\n"
        "retry_backoff_seconds = 11\n"
        "timeout_seconds = 42.5\n"
        'log_level = "debug"\n',
        encoding="utf-8",
    )
    (version_dir / "publish.json").write_text(
        f'{{"automation_id":"demo","version":1,"source_task_path":"/tmp/task","snapshot_dir":"{version_dir}"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {
            "ok": True,
            "data": {
                "id": "demo",
                "name": "Demo Live",
                "description": "Live",
                "version": "2",
                "task_path": str(version_dir / "task.py"),
                "task_meta_path": str(version_dir / "task.meta.json"),
                "entrypoint": "run",
                "schedule_kind": "interval",
                "schedule_payload": {
                    "mode": "interval",
                    "interval_seconds": 900,
                    "timezone": "Asia/Shanghai",
                },
                "timezone": "Asia/Shanghai",
                "output_dir": str(tmp_path / "home" / "automations" / "demo"),
                "result_json_path": str(tmp_path / "home" / "automations" / "demo" / "result.json"),
                "stdout_mode": "text",
                "input_overrides": {"url": "https://example.com"},
                "before_run_hooks": ["echo before"],
                "after_success_hooks": ["echo success"],
                "after_failure_hooks": ["echo failure"],
                "retry_attempts": 2,
                "retry_backoff_seconds": 11,
                "timeout_seconds": 42.5,
                "log_level": "debug",
                "enabled": True,
                "definition_status": "valid",
                "latest_run": {"status": "success"},
            },
        },
    )

    payload = json.loads(
        run_automation_command(
            Namespace(automation_subcommand="inspect", automation_id="demo", version=1)
        )
    )

    snapshot_keys = set(payload["data"]["snapshot_config"])
    live_keys = set(payload["data"]["live_config"])

    assert snapshot_keys == live_keys
    assert payload["data"]["snapshot_config"]["log_level"] == "debug"
    assert payload["data"]["live_config"]["retry_backoff_seconds"] == 11
    assert payload["data"]["live_config"]["log_level"] == "debug"
```

Run:

```bash
uv run pytest tests/unit/test_automation_commands.py -v
```

Expected: FAIL because `snapshot_config` and `live_config` are still built by
different code paths with different field sets and runtime defaults.

- [x] **Step 2: Route inspect config rendering through shared projections**

Update `src/browser_cli/commands/automation.py`:

```python
from browser_cli.automation.projections import (
    manifest_to_config_payload,
    payload_to_persisted_definition,
    persisted_definition_to_config_payload,
)
```

Replace `_snapshot_manifest_to_automation_payload()` with:

```python
def _snapshot_manifest_to_automation_payload(manifest: AutomationManifest) -> dict[str, object]:
    return manifest_to_config_payload(manifest)
```

Inside `run_automation_command()` `inspect` handling, derive `live_config` from
the shared projection too:

```python
        live_automation_data = dict(payload.get("data") or {})
        live_config = (
            persisted_definition_to_config_payload(
                payload_to_persisted_definition(live_automation_data)
            )
            if live_automation_data
            else None
        )
```

And return:

```python
                    "snapshot_config": snapshot_config,
                    "snapshot_config_error": snapshot_config_error,
                    "live_config": live_config,
```

Keep `latest_run`, `versions`, and `summary` as separate operational sections.

- [x] **Step 3: Run the inspect command suite**

Run:

```bash
uv run pytest tests/unit/test_automation_commands.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/browser_cli/commands/automation.py tests/unit/test_automation_commands.py
git commit -m "fix: align automation inspect config views"
```

## Task 5: Run Full Validation And Mark The Plan Complete

**Files:**
- Modify: `docs/superpowers/plans/2026-04-14-automation-manifest-roundtrip-implementation-plan.md`
- Test: `tests/unit/test_automation_projections.py`
- Test: `tests/unit/test_task_runtime_automation.py`
- Test: `tests/unit/test_automation_publish.py`
- Test: `tests/unit/test_automation_api.py`
- Test: `tests/unit/test_automation_commands.py`

- [x] **Step 1: Run the focused automation round-trip suites**

Run:

```bash
uv run pytest \
  tests/unit/test_automation_projections.py \
  tests/unit/test_task_runtime_automation.py \
  tests/unit/test_automation_publish.py \
  tests/unit/test_automation_api.py \
  tests/unit/test_automation_commands.py -v
```

Expected: PASS

- [x] **Step 2: Run repository validation**

Run:

```bash
./scripts/lint.sh
./scripts/test.sh
./scripts/guard.sh
```

Expected: all three scripts exit `0`.

- [x] **Step 3: Update this plan file to mark the completed steps**

Update the completed steps in this file:

```markdown
- [x] **Step 1: Run the focused automation round-trip suites**
- [x] **Step 2: Run repository validation**
- [x] **Step 3: Update this plan file to mark the completed steps**
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-04-14-automation-manifest-roundtrip-implementation-plan.md
git commit -m "docs: mark automation manifest round-trip plan complete"
```

## Self-Review

Spec coverage:

- shared projection layer for manifest/persistence/publish/export/inspect: covered by Tasks 2, 3, and 4
- semantic consistency over raw text preservation: covered by Task 1 regression style and Task 3 export/publish round-trip checks
- publish preserves supported fields while allowing path remapping: covered by Tasks 1 and 3
- import/export round-trip through persisted live state: covered by Tasks 2 and 3
- `inspect --version` snapshot/live config parity: covered by Task 4
- supported field set coverage for hooks/runtime/schedule/inputs/outputs: covered by Tasks 1, 3, and 4

Placeholder scan:

- no `TODO`/`TBD` placeholders remain
- every code-edit step includes concrete code
- every test step includes an exact command and expected result

Type consistency:

- projection helper names are consistent across tasks:
  `manifest_to_persisted_definition`
  `payload_to_persisted_definition`
  `persisted_definition_to_manifest_toml`
  `manifest_to_snapshot_manifest_toml`
  `manifest_to_config_payload`
  `persisted_definition_to_config_payload`
- `live_config` and `snapshot_config` are explicitly routed through the same
  projection family rather than separate ad hoc dict builders
