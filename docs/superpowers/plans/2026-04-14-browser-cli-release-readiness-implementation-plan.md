# Browser CLI Release Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make automation publish/import/export/inspect preserve supported manifest fields, enforce automation run timeouts, and restore one-shot read fallback reporting before the first public release.

**Architecture:** Keep the current task/automation/daemon architecture and tighten the release contract around one rule: a published automation version is defined by the immutable snapshot manifest in `~/.browser-cli/automations/<automation-id>/versions/<version>/`. Align loader, models, publisher, commands, API, and service runtime to that truth model, while keeping local `task run` semantics unchanged and limiting fallback-profile reporting changes to the read path.

**Tech Stack:** Python 3.10+, argparse CLI handlers, TOML via `tomllib`/`tomli`, SQLite-backed automation persistence, pytest unit/integration tests

---

## File Structure

### Files to modify

- `src/browser_cli/automation/models.py`
  - Add missing runtime schema fields so manifest loading, persistence conversion, export, and inspect all share one supported field set.
- `src/browser_cli/automation/loader.py`
  - Parse the full supported manifest schema, especially `runtime.retry_backoff_seconds`.
- `src/browser_cli/automation/publisher.py`
  - Load source `automation.toml` when present, generate defaults only when absent, snapshot the resolved manifest, and return `manifest_source`.
- `src/browser_cli/commands/automation.py`
  - Surface `manifest_source` on publish and split inspect output into `snapshot_config` and `live_config`.
- `src/browser_cli/automation/api/server.py`
  - Accept and serialize the full supported automation field set, including `stdout_mode` and `retry_backoff_seconds`.
- `src/browser_cli/automation/service/runtime.py`
  - Enforce run-level timeout behavior and prevent timeout-triggered retries.
- `src/browser_cli/errors.py`
  - Add a dedicated timeout error or code path suitable for automation-run timeout failures.
- `src/browser_cli/daemon/browser_service.py`
  - Restore fallback profile metadata on `read_page`.
- `README.md`
  - Update durable release-model and inspect/timeout guidance.
- `AGENTS.md`
  - Update durable navigation and debugging guidance for publish truth and inspect dual-view behavior.

### Files to create or extend in tests

- `tests/unit/test_automation_publish.py`
  - Add publish tests covering source manifest preservation and generated-defaults fallback.
- `tests/unit/test_task_runtime_automation.py`
  - Add loader/model tests for runtime schema parity.
- `tests/unit/test_automation_commands.py`
  - Add publish/inspect command output tests for `manifest_source`, `snapshot_config`, and `live_config`.
- `tests/unit/test_automation_api.py`
  - Add import/export/API parity tests for `stdout_mode`, `retry_backoff_seconds`, and timeout fields.
- `tests/unit/test_automation_service.py`
  - Add runtime timeout and no-retry-on-timeout coverage.
- `tests/unit/test_task_runtime_client_read.py`
  - Add read fallback metadata propagation coverage for the daemon-backed path.
- `tests/integration/test_task_runtime_read.py`
  - Extend daemon-backed read integration coverage for fallback metadata on the stable fixture path.

## Task 1: Align Manifest Schema And Persistence Payloads

**Files:**
- Modify: `src/browser_cli/automation/models.py`
- Modify: `src/browser_cli/automation/loader.py`
- Modify: `src/browser_cli/commands/automation.py`
- Modify: `src/browser_cli/automation/api/server.py`
- Test: `tests/unit/test_task_runtime_automation.py`
- Test: `tests/unit/test_automation_api.py`

- [ ] **Step 1: Write the failing schema-parity tests**

```python
def test_load_automation_manifest_preserves_retry_backoff_and_stdout(tmp_path: Path) -> None:
    manifest_path = tmp_path / "automation.toml"
    manifest_path.write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n'
        "[outputs]\n"
        'stdout = "text"\n'
        "[runtime]\n"
        "retry_attempts = 2\n"
        "retry_backoff_seconds = 7\n"
        "timeout_seconds = 12.5\n",
        encoding="utf-8",
    )
    (tmp_path / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (tmp_path / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )

    manifest = load_automation_manifest(manifest_path)
    persisted = manifest_to_persisted_definition(manifest)

    assert manifest.outputs.stdout == "text"
    assert manifest.runtime.retry_backoff_seconds == 7
    assert manifest.runtime.timeout_seconds == 12.5
    assert persisted.stdout_mode == "text"
    assert persisted.retry_backoff_seconds == 7
    assert persisted.timeout_seconds == 12.5
```

```python
def test_payload_to_automation_preserves_stdout_and_retry_backoff() -> None:
    persisted = _payload_to_automation(
        {
            "id": "demo",
            "name": "Demo",
            "task_path": "/tmp/task.py",
            "task_meta_path": "/tmp/task.meta.json",
            "output_dir": "/tmp/out",
            "stdout_mode": "text",
            "retry_attempts": 1,
            "retry_backoff_seconds": 9,
            "timeout_seconds": 4.0,
        }
    )

    assert persisted.stdout_mode == "text"
    assert persisted.retry_backoff_seconds == 9
    assert persisted.timeout_seconds == 4.0
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/unit/test_task_runtime_automation.py tests/unit/test_automation_api.py -k "retry_backoff or stdout" -v`

Expected: FAIL because `AutomationRuntime` does not expose `retry_backoff_seconds` and one or more command/API payload paths still drop `stdout_mode` or retry-backoff data.

- [ ] **Step 3: Implement the schema and payload alignment**

Update `src/browser_cli/automation/models.py`:

```python
@dataclass(slots=True, frozen=True)
class AutomationRuntime:
    timeout_seconds: float | None = None
    retry_attempts: int = 0
    retry_backoff_seconds: int = 0
    log_level: str = "info"
```

```python
def manifest_to_persisted_definition(
    manifest: AutomationManifest,
    *,
    enabled: bool = False,
) -> PersistedAutomationDefinition:
    return PersistedAutomationDefinition(
        id=manifest.automation.id,
        name=manifest.automation.name,
        task_path=manifest.task.path,
        task_meta_path=manifest.task.meta_path,
        output_dir=manifest.outputs.artifact_dir,
        description=manifest.automation.description,
        version=str(manifest.automation.version),
        entrypoint=manifest.task.entrypoint,
        enabled=enabled,
        schedule_kind=str(manifest.schedule.get("mode") or "manual"),
        schedule_payload=dict(manifest.schedule),
        timezone=str(manifest.schedule.get("timezone") or "UTC"),
        result_json_path=manifest.outputs.result_json_path,
        stdout_mode=manifest.outputs.stdout,
        input_overrides=dict(manifest.inputs),
        before_run_hooks=manifest.hooks.before_run,
        after_success_hooks=manifest.hooks.after_success,
        after_failure_hooks=manifest.hooks.after_failure,
        retry_attempts=manifest.runtime.retry_attempts,
        retry_backoff_seconds=manifest.runtime.retry_backoff_seconds,
        timeout_seconds=manifest.runtime.timeout_seconds,
    )
```

Update `src/browser_cli/automation/loader.py`:

```python
        runtime=AutomationRuntime(
            timeout_seconds=float((data.get("runtime") or {})["timeout_seconds"])
            if (data.get("runtime") or {}).get("timeout_seconds") is not None
            else None,
            retry_attempts=int((data.get("runtime") or {}).get("retry_attempts") or 0),
            retry_backoff_seconds=int(
                (data.get("runtime") or {}).get("retry_backoff_seconds") or 0
            ),
            log_level=str((data.get("runtime") or {}).get("log_level") or "info"),
        ),
```

Update `src/browser_cli/commands/automation.py` and `src/browser_cli/automation/api/server.py` so all automation payload builders include:

```python
        "stdout_mode": manifest.outputs.stdout,
        "retry_backoff_seconds": int(manifest.runtime.retry_backoff_seconds or 0),
```

and retain those values when building snapshot/live inspect payloads and persisted automations.

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run: `uv run pytest tests/unit/test_task_runtime_automation.py tests/unit/test_automation_api.py -k "retry_backoff or stdout" -v`

Expected: PASS with the new runtime field and payload parity tests green.

- [ ] **Step 5: Commit the schema-alignment change**

```bash
git add tests/unit/test_task_runtime_automation.py tests/unit/test_automation_api.py src/browser_cli/automation/models.py src/browser_cli/automation/loader.py src/browser_cli/commands/automation.py src/browser_cli/automation/api/server.py
git commit -m "fix: align automation manifest schema across payload paths"
```

## Task 2: Make Publish Snapshot The Source Manifest Truth

**Files:**
- Modify: `src/browser_cli/automation/publisher.py`
- Modify: `src/browser_cli/commands/automation.py`
- Test: `tests/unit/test_automation_publish.py`
- Test: `tests/unit/test_automation_commands.py`

- [ ] **Step 1: Write the failing publish-contract tests**

```python
def test_publish_task_dir_preserves_source_manifest_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
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
        "[inputs]\n"
        'url = "https://example.com"\n'
        "[schedule]\n"
        'mode = "manual"\n'
        'timezone = "Asia/Shanghai"\n'
        "[outputs]\n"
        'artifact_dir = "artifacts"\n'
        'result_json_path = "artifacts/result.json"\n'
        'stdout = "text"\n'
        "[runtime]\n"
        "retry_attempts = 1\n"
        "retry_backoff_seconds = 7\n",
        encoding="utf-8",
    )

    published = publish_task_dir(task_dir, app_paths=get_app_paths())
    manifest = load_automation_manifest(published.manifest_path)

    assert published.manifest_source == "task_dir"
    assert manifest.inputs == {"url": "https://example.com"}
    assert manifest.schedule["timezone"] == "Asia/Shanghai"
    assert manifest.outputs.result_json_path is not None
    assert manifest.outputs.stdout == "text"
    assert manifest.runtime.retry_backoff_seconds == 7
```

```python
def test_publish_task_dir_generates_defaults_when_manifest_is_absent(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )

    published = publish_task_dir(task_dir, app_paths=get_app_paths())
    manifest = load_automation_manifest(published.manifest_path)

    assert published.manifest_source == "generated_defaults"
    assert manifest.schedule["timezone"] == "UTC"
    assert manifest.inputs == {}
```

```python
def test_run_automation_publish_returns_manifest_source(monkeypatch, tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
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
        'meta_path = "task.meta.json"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "browser_cli.commands.automation.ensure_automation_service_running",
        lambda: None,
    )
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {"ok": True, "data": {"id": "demo"}},
    )
    args = Namespace(automation_subcommand="publish", path=str(task_dir))
    payload = json.loads(run_automation_command(args))
    assert payload["data"]["published"]["manifest_source"] == "task_dir"
```

- [ ] **Step 2: Run the targeted publish tests to verify they fail**

Run: `uv run pytest tests/unit/test_automation_publish.py tests/unit/test_automation_commands.py -k "manifest_source or preserves_source_manifest or generates_defaults" -v`

Expected: FAIL because publish currently regenerates the snapshot manifest from defaults and does not return `manifest_source`.

- [ ] **Step 3: Implement source-manifest publish behavior**

Update `src/browser_cli/automation/publisher.py`:

```python
@dataclass(slots=True, frozen=True)
class PublishedAutomation:
    automation_id: str
    automation_name: str
    version: int
    snapshot_dir: Path
    manifest_path: Path
    output_dir: Path
    manifest_source: str
```

```python
def publish_task_dir(task_dir: Path, *, app_paths: AppPaths) -> PublishedAutomation:
    metadata = validate_task_dir(task_dir)
    source_manifest_path = task_dir / "automation.toml"
    if source_manifest_path.exists():
        source_manifest = load_automation_manifest(source_manifest_path)
        manifest_source = "task_dir"
        rendered_manifest = render_automation_manifest_from_manifest(
            source_manifest,
            version=version,
            task_path=task_path,
            task_meta_path=task_meta_path,
            output_dir=automation_root,
        )
    else:
        manifest_source = "generated_defaults"
        rendered_manifest = render_automation_manifest(
            automation_id=automation_id,
            name=automation_name,
            version=version,
            task_path=task_path,
            task_meta_path=task_meta_path,
            output_dir=automation_root,
        )
    manifest_path.write_text(rendered_manifest, encoding="utf-8")
    return PublishedAutomation(
        automation_id=automation_id,
        automation_name=automation_name,
        version=version,
        snapshot_dir=snapshot_dir,
        manifest_path=manifest_path,
        output_dir=automation_root,
        manifest_source=manifest_source,
    )
```

Update `src/browser_cli/commands/automation.py` publish response:

```python
                    "published": {
                        "automation_id": published.automation_id,
                        "automation_name": published.automation_name,
                        "version": published.version,
                        "manifest_source": published.manifest_source,
                        "source_task_dir": str(source_task_dir),
                        "snapshot_dir": str(published.snapshot_dir),
                        "manifest_path": str(published.manifest_path),
                    },
```

- [ ] **Step 4: Run the targeted publish tests to verify they pass**

Run: `uv run pytest tests/unit/test_automation_publish.py tests/unit/test_automation_commands.py -k "manifest_source or preserves_source_manifest or generates_defaults" -v`

Expected: PASS with snapshot manifests preserving source configuration and CLI publish output reporting the manifest source.

- [ ] **Step 5: Commit the publish-contract change**

```bash
git add tests/unit/test_automation_publish.py tests/unit/test_automation_commands.py src/browser_cli/automation/publisher.py src/browser_cli/commands/automation.py
git commit -m "fix: preserve source manifest during automation publish"
```

## Task 3: Split Inspect Into Snapshot And Live Configuration Views

**Files:**
- Modify: `src/browser_cli/commands/automation.py`
- Test: `tests/unit/test_automation_commands.py`

- [ ] **Step 1: Write the failing inspect dual-view tests**

```python
def test_automation_inspect_version_returns_snapshot_and_live_config(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    version_dir = tmp_path / "home" / "automations" / "demo" / "versions" / "1"
    version_dir.mkdir(parents=True)
    (version_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (version_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    (version_dir / "automation.toml").write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo Snapshot"\n'
        'version = "1"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n'
        "[outputs]\n"
        'stdout = "text"\n',
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
                "version": "2",
                "task_path": str(version_dir / "task.py"),
                "task_meta_path": str(version_dir / "task.meta.json"),
                "schedule_kind": "manual",
                "schedule_payload": {"mode": "manual"},
                "stdout_mode": "json",
                "latest_run": {"status": "success"},
            },
        },
    )
    args = Namespace(automation_subcommand="inspect", automation_id="demo", version=1)
    payload = json.loads(run_automation_command(args))
    assert payload["data"]["snapshot_config"]["name"] == "Demo Snapshot"
    assert payload["data"]["snapshot_config"]["stdout_mode"] == "text"
    assert payload["data"]["live_config"]["name"] == "Demo Live"
```

```python
def test_automation_inspect_version_reports_snapshot_config_error(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    version_dir = tmp_path / "home" / "automations" / "demo" / "versions" / "1"
    version_dir.mkdir(parents=True)
    (version_dir / "automation.toml").write_text("[automation]\n", encoding="utf-8")
    (version_dir / "publish.json").write_text(
        f'{{"automation_id":"demo","version":1,"source_task_path":"/tmp/task","snapshot_dir":"{version_dir}"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "browser_cli.commands.automation.request_automation_service",
        lambda method, path, body=None, start_if_needed=True: {
            "ok": True,
            "data": {"id": "demo", "name": "Demo Live", "latest_run": None},
        },
    )
    args = Namespace(automation_subcommand="inspect", automation_id="demo", version=1)
    payload = json.loads(run_automation_command(args))
    assert payload["data"]["snapshot_config"] is None
    assert "snapshot_config_error" in payload["data"]
```

- [ ] **Step 2: Run the inspect tests to verify they fail**

Run: `uv run pytest tests/unit/test_automation_commands.py -k "snapshot_config or live_config" -v`

Expected: FAIL because inspect currently merges snapshot data into a single automation payload and falls back to live config when snapshot loading fails.

- [ ] **Step 3: Implement inspect dual-view behavior**

Update `src/browser_cli/commands/automation.py` to return separate sections:

```python
        return render_json_payload(
            {
                "ok": True,
                "data": {
                    "snapshot_config": snapshot_config,
                    "snapshot_config_error": snapshot_config_error,
                    "live_config": live_automation_data,
                    "versions": versions,
                    "selected_version": selected,
                    "latest_run": selected_latest_run,
                    "summary": _build_inspect_summary(
                        args.automation_id,
                        live_automation_data,
                        versions,
                        selected,
                        selected_latest_run,
                    ),
                },
                "meta": {"action": "automation-inspect"},
            }
        )
```

Update snapshot loading helpers so they report snapshot-manifest failures explicitly instead of silently falling back:

```python
def _load_snapshot_manifest(path: Path) -> tuple[AutomationManifest | None, str | None]:
    if not path.exists():
        return None, None
    try:
        return load_automation_manifest(path), None
    except InvalidInputError as exc:
        return None, str(exc)
```

- [ ] **Step 4: Run the inspect tests to verify they pass**

Run: `uv run pytest tests/unit/test_automation_commands.py -k "snapshot_config or live_config" -v`

Expected: PASS with inspect returning separate `snapshot_config`, `live_config`, and `snapshot_config_error` fields.

- [ ] **Step 5: Commit the inspect split**

```bash
git add tests/unit/test_automation_commands.py src/browser_cli/commands/automation.py
git commit -m "feat: split automation inspect into snapshot and live views"
```

## Task 4: Enforce Run-Level Timeout And Disable Timeout Retries

**Files:**
- Modify: `src/browser_cli/automation/service/runtime.py`
- Modify: `src/browser_cli/errors.py`
- Test: `tests/unit/test_automation_service.py`

- [ ] **Step 1: Write the failing timeout tests**

```python
def test_automation_service_marks_run_failed_on_timeout(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "import time\n"
        "def run(flow, inputs):\n"
        "    time.sleep(0.3)\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    store = AutomationStore(tmp_path / "automations.db")
    store.upsert_automation(
        PersistedAutomationDefinition(
            id="demo",
            name="Demo",
            task_path=task_dir / "task.py",
            task_meta_path=task_dir / "task.meta.json",
            output_dir=tmp_path / "out",
            timeout_seconds=0.05,
        )
    )
    run = store.create_run("demo", trigger_type="manual")
    runtime = AutomationServiceRuntime(store=store)

    runtime._execute_run(run.run_id)
    updated = store.get_run(run.run_id)

    assert updated.status == "failed"
    assert updated.error_code == "AUTOMATION_RUN_TIMEOUT"
    assert "timed out" in str(updated.error_message).lower()
```

```python
def test_automation_service_does_not_retry_timeout_failure(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "import time\n"
        "def run(flow, inputs):\n"
        "    time.sleep(0.3)\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    store = AutomationStore(tmp_path / "automations.db")
    store.upsert_automation(
        PersistedAutomationDefinition(
            id="demo",
            name="Demo",
            task_path=task_dir / "task.py",
            task_meta_path=task_dir / "task.meta.json",
            output_dir=tmp_path / "out",
            timeout_seconds=0.05,
            retry_attempts=3,
        )
    )
    run = store.create_run("demo", trigger_type="manual")
    runtime = AutomationServiceRuntime(store=store)
    runtime._execute_run(run.run_id)
    runs = store.list_runs("demo", limit=10)
    assert [run.status for run in runs] == ["failed"]
```

- [ ] **Step 2: Run the timeout tests to verify they fail**

Run: `uv run pytest tests/unit/test_automation_service.py -k "timeout" -v`

Expected: FAIL because `timeout_seconds` is currently not enforced and timed-out runs still complete successfully.

- [ ] **Step 3: Implement run-level timeout enforcement**

Add a dedicated timeout error in `src/browser_cli/errors.py`:

```python
class AutomationRunTimeoutError(OperationFailedError):
    def __init__(self, message: str = "Automation run timed out.") -> None:
        super().__init__(message, error_code="AUTOMATION_RUN_TIMEOUT")
```

Update `src/browser_cli/automation/service/runtime.py` to run the main execution path under a timeout:

```python
def _run_with_timeout(self, automation, fn):
    if automation.timeout_seconds is None or automation.timeout_seconds <= 0:
        return fn()
    result_box: dict[str, Any] = {}
    error_box: dict[str, BaseException] = {}

    def _target() -> None:
        try:
            result_box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            error_box["error"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=automation.timeout_seconds)
    if thread.is_alive():
        raise AutomationRunTimeoutError(
            f"Automation run timed out after {automation.timeout_seconds} seconds."
        )
    if "error" in error_box:
        raise error_box["error"]
    return result_box.get("value")
```

Wrap the existing execution path so timeout is enforced around daemon readiness, hooks, and task execution, and gate retry scheduling:

```python
                self._run_with_timeout(
                    automation,
                    lambda: self._execute_run_main(run_id, automation, run, log_handle, run_dir),
                )
```

```python
                timed_out = error_code == "AUTOMATION_RUN_TIMEOUT"
                if not timed_out and automation.retry_attempts > run.attempt_number:
                    retry_run = self.store.retry_run(run_id)
                    self.store.add_run_event(
                        retry_run.run_id,
                        AutomationRunEvent(
                            run_id=retry_run.run_id,
                            event_type="retry_scheduled",
                            message=f"Retry scheduled after failed run {run_id}.",
                        ),
                    )
```

- [ ] **Step 4: Run the timeout tests to verify they pass**

Run: `uv run pytest tests/unit/test_automation_service.py -k "timeout" -v`

Expected: PASS with timed-out runs marked failed and no extra retry runs created.

- [ ] **Step 5: Commit the timeout enforcement**

```bash
git add tests/unit/test_automation_service.py src/browser_cli/automation/service/runtime.py src/browser_cli/errors.py
git commit -m "fix: enforce automation run timeouts"
```

## Task 5: Restore Read Fallback Metadata And Update Durable Docs

**Files:**
- Modify: `src/browser_cli/daemon/browser_service.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Test: `tests/unit/test_task_runtime_client_read.py`
- Test: `tests/integration/test_task_runtime_read.py`

- [ ] **Step 1: Write the failing fallback-reporting tests**

```python
def test_run_read_request_preserves_daemon_fallback_metadata() -> None:
    payload = {
        "ok": True,
        "data": {
            "body": "<html></html>",
            "used_fallback_profile": True,
            "fallback_profile_dir": "/tmp/browser-cli/default-profile",
            "fallback_reason": "Chrome profile appears to be in use.",
        },
    }
    with patch("browser_cli.task_runtime.read.send_command", return_value=payload):
        result = asyncio.run(
            run_read_request(ReadRequest(url="https://example.com", output_mode="html"))
        )

    assert result.used_fallback_profile is True
    assert result.fallback_profile_dir == "/tmp/browser-cli/default-profile"
    assert result.fallback_reason == "Chrome profile appears to be in use."
```

```python
def test_task_runtime_read_daemon_path_reports_fallback_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    chrome_environment = _build_chrome_environment(tmp_path)
    with run_fixture_server() as base_url:
        payload = send_command(
            "read-page",
            {
                "url": f"{base_url}/static",
                "output_mode": "html",
                "chrome_environment": {
                    "executable_path": None,
                    "user_data_dir": str(chrome_environment.user_data_dir),
                    "profile_directory": chrome_environment.profile_directory,
                    "profile_name": chrome_environment.profile_name,
                    "source": "fallback",
                    "fallback_reason": "Chrome profile appears to be in use.",
                },
            },
        )
        assert payload["data"]["used_fallback_profile"] is True
        assert payload["data"]["fallback_reason"] == "Chrome profile appears to be in use."
        send_command("stop", start_if_needed=False)
```

- [ ] **Step 2: Run the fallback tests to verify they fail**

Run: `uv run pytest tests/unit/test_task_runtime_client_read.py tests/integration/test_task_runtime_read.py -k "fallback" -v`

Expected: FAIL because daemon `read_page` currently drops fallback profile metadata on the daemon-backed read path.

- [ ] **Step 3: Restore read fallback metadata and update docs**

Update `src/browser_cli/daemon/browser_service.py`:

```python
            response = {
                "page_id": page_id,
                "body": body,
                "output_mode": output_mode,
                "url": str(page["url"]),
            }
            chrome_environment = self._playwright.chrome_environment
            if chrome_environment is not None:
                response["used_fallback_profile"] = chrome_environment.source == "fallback"
                if chrome_environment.source == "fallback":
                    response["fallback_profile_dir"] = str(chrome_environment.user_data_dir)
                    response["fallback_reason"] = chrome_environment.fallback_reason
                if chrome_environment.profile_name:
                    response["profile_name"] = chrome_environment.profile_name
                response["profile_directory"] = chrome_environment.profile_directory
            return response
```

Update `README.md` with durable release-model notes such as:

```markdown
- `automation publish` snapshots source `automation.toml` when present; if it is
  absent, Browser CLI publishes generated defaults and reports that explicitly.
- `automation inspect --version <n>` shows the immutable snapshot configuration
  separately from the current live automation-service configuration.
- `runtime.timeout_seconds` is the total wall-clock timeout for one automation
  run, not just the `task.py` function body.
```

Update `AGENTS.md` with durable navigation notes such as:

```markdown
- If the user reports publish/config drift, inspect `src/browser_cli/automation/publisher.py`,
  `src/browser_cli/commands/automation.py`, and the snapshot manifest under
  `~/.browser-cli/automations/<automation-id>/versions/<version>/automation.toml`.
- `inspect --version` must treat the snapshot manifest as historical truth and
  render current persisted automation state separately.
```

- [ ] **Step 4: Run the fallback and repository validation tests**

Run: `uv run pytest tests/unit/test_task_runtime_client_read.py tests/integration/test_task_runtime_read.py -k "fallback" -v`

Expected: PASS with daemon-backed read preserving fallback metadata again.

Run: `./scripts/check.sh`

Expected: PASS with lint, test, and guard all green.

- [ ] **Step 5: Commit the fallback and docs update**

```bash
git add tests/unit/test_task_runtime_client_read.py tests/integration/test_task_runtime_read.py src/browser_cli/daemon/browser_service.py README.md AGENTS.md
git commit -m "fix: restore read fallback reporting and document release contract"
```

## Self-Review

### Spec Coverage

- Publish preserves source manifest truth: covered by Task 2.
- Generated-defaults fallback when source manifest is absent: covered by Task 2.
- Manifest schema parity and round-trip support for supported fields: covered by Task 1.
- Inspect separation between snapshot and live config: covered by Task 3.
- Timeout is a run-level total timeout with no retry-on-timeout: covered by Task 4.
- Read fallback reporting restored only for the read path: covered by Task 5.
- Durable docs and agent guidance updates: covered by Task 5.

### Placeholder Scan

- No unresolved placeholder markers remain.
- Each task includes concrete files, test code, commands, expected outcomes, and commit commands.

### Type Consistency

- `retry_backoff_seconds`, `stdout_mode`, `manifest_source`, `snapshot_config`, `live_config`, and `AUTOMATION_RUN_TIMEOUT` are used consistently across the tasks.
- Timeout scope remains explicitly limited to automation-service execution and does not leak into `task run`.
