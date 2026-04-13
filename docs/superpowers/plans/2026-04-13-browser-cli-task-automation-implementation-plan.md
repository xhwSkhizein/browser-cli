# Browser CLI Task And Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the public `workflow` surface with a task-first local UX and an automation-first publish/runtime UX, including snapshot-based publication and service execution from immutable automation versions.

**Architecture:** Keep `task.py` execution on top of `browser_cli.task_runtime`, but split public concerns into `task` and `automation`. Add a new `browser_cli.automation` package for manifests, persistence, service runtime, API, and UI; add a task command surface that runs and validates source task directories directly. Remove the public `workflow` CLI and retire the legacy manifest and service names instead of preserving compatibility shims.

**Tech Stack:** Python 3.10+, argparse, dataclasses, pathlib, sqlite3, local HTTP server, existing Browser CLI daemon/task runtime, pytest

---

## File Structure

### Create

- `src/browser_cli/commands/task.py`
  - User-facing `task run` and `task validate` command handlers.
- `src/browser_cli/commands/automation.py`
  - User-facing `automation publish/import/export/ui/status/stop` command handlers.
- `src/browser_cli/task_runtime/entrypoint.py`
  - Shared task module loading, input parsing, task execution, and contract validation helpers used by both `task` and `automation`.
- `src/browser_cli/automation/__init__.py`
  - Public automation package exports.
- `src/browser_cli/automation/models.py`
  - Automation manifest, persisted definition, version record, and run record dataclasses.
- `src/browser_cli/automation/loader.py`
  - `automation.toml` load/validate helpers.
- `src/browser_cli/automation/publisher.py`
  - Source-task publication, snapshot creation, and service import helpers.
- `src/browser_cli/automation/service/__init__.py`
  - Automation service exports.
- `src/browser_cli/automation/service/client.py`
  - Local service client and run-info helpers.
- `src/browser_cli/automation/service/runtime.py`
  - Background service scheduler/executor that runs snapshot tasks.
- `src/browser_cli/automation/service/__main__.py`
  - Service process entrypoint.
- `src/browser_cli/automation/persistence/__init__.py`
  - Persistence exports.
- `src/browser_cli/automation/persistence/store.py`
  - SQLite persistence for automations, versions, runs, and run events.
- `src/browser_cli/automation/api/__init__.py`
  - API exports.
- `src/browser_cli/automation/api/server.py`
  - Local API and HTML handler for automation service.
- `src/browser_cli/automation/web/__init__.py`
  - Web UI exports.
- `src/browser_cli/automation/web/assets.py`
  - Automation UI HTML/JS/CSS.
- `tests/unit/test_task_commands.py`
  - Task CLI command behavior and validation failures.
- `tests/unit/test_task_entrypoint.py`
  - Task entrypoint loading/contract tests.
- `tests/unit/test_automation_loader.py`
  - `automation.toml` load/validate tests.
- `tests/unit/test_automation_publish.py`
  - Snapshot publication tests.
- `tests/unit/test_automation_api.py`
  - Automation API CRUD/import/export tests.
- `tests/unit/test_automation_service.py`
  - Automation store/runtime tests.
- `tests/integration/test_task_cli.py`
  - End-to-end task run/validate against local fixtures.
- `tests/integration/test_automation_cli.py`
  - End-to-end automation publish/export and service interactions.
- `docs/examples/task-and-automation.md`
  - Replaces workflow-oriented example doc.

### Modify

- `src/browser_cli/cli/main.py`
  - Replace `workflow` parser with `task` and `automation`.
- `src/browser_cli/constants.py`
  - Add task and automation paths; remove legacy workflow path names.
- `src/browser_cli/commands/status.py`
  - Report automation service status instead of workflow service status.
- `src/browser_cli/error_codes.py`
  - Replace workflow-prefixed public error codes with task/automation equivalents.
- `src/browser_cli/errors.py`
  - Replace workflow-specific exception classes and add task/automation-specific errors where needed.
- `src/browser_cli/task_runtime/models.py`
  - Keep metadata schema validation and rename execution context fields from workflow-specific names to automation-neutral names.
- `README.md`
  - Reframe the product around task and automation.
- `AGENTS.md`
  - Update durable navigation guidance, code map entries, and debugging paths.
- `skills/browser-cli-explore-delivery/SKILL.md`
  - Require canonical task templates and `browser-cli task validate`.
- `skills/browser-cli-explore-delivery/references/preflight-and-runtime.md`
  - Update task execution/publish guidance.
- `scripts/guards/product_contracts.py`
  - Freeze the new top-level `task` and `automation` surfaces.
- `scripts/guards/architecture.py`
  - Replace the `workflow` package boundary with `automation`.
- `scripts/guards/docs_sync.py`
  - Update required AGENTS/README phrases.
- `docs/smoke-checklist.md`
  - Replace workflow smoke checks with task/automation smoke checks.
- `tasks/interactive_reveal_capture/automation.toml`
  - Published example manifest after rename.
- `tasks/lazy_scroll_capture/automation.toml`
  - Published example manifest after rename.
- `tests/unit/test_python_compatibility.py`
  - Import automation modules instead of workflow modules.

### Delete

- `src/browser_cli/commands/workflow.py`
- `src/browser_cli/workflow/`
- `tests/unit/test_workflow_api.py`
- `tests/unit/test_workflow_service.py`
- `tests/unit/test_task_runtime_workflow.py`
- `tests/integration/test_workflow_runner.py`
- `docs/examples/task-and-workflow.md`
- `tasks/interactive_reveal_capture/workflow.toml`
- `tasks/lazy_scroll_capture/workflow.toml`

Deletion should happen only after the new `task` and `automation` replacements are green.

### Notes

- Do not add compatibility aliases like `browser-cli workflow ...`.
- Do not migrate `workflows.db` or old workflow run directories in this change.
- The new service should use fresh automation-specific path names and data files.

### Task 1: Add App Paths And Public Parser Skeleton

**Files:**
- Modify: `src/browser_cli/constants.py`
- Modify: `src/browser_cli/cli/main.py`
- Test: `tests/unit/test_task_commands.py`

- [ ] **Step 1: Write the failing parser and path tests**

```python
from browser_cli.cli.main import build_parser
from browser_cli.constants import get_app_paths


def test_build_parser_exposes_task_and_automation_commands(monkeypatch, tmp_path):
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path))
    parser = build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")
    assert "task" in subparsers.choices
    assert "automation" in subparsers.choices
    assert "workflow" not in subparsers.choices


def test_get_app_paths_exposes_task_and_automation_roots(monkeypatch, tmp_path):
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path))
    paths = get_app_paths()
    assert paths.tasks_dir == tmp_path / "tasks"
    assert paths.automations_dir == tmp_path / "automations"
    assert paths.automation_db_path == tmp_path / "automations.db"
```

- [ ] **Step 2: Run the parser/path tests to verify they fail**

Run: `pytest tests/unit/test_task_commands.py -k "parser_exposes_task_and_automation or app_paths_exposes_task_and_automation_roots" -v`
Expected: FAIL because `build_parser()` still exposes `workflow` and `AppPaths` does not define task/automation fields.

- [ ] **Step 3: Add task and automation path fields in `constants.py`**

```python
@dataclass(slots=True, frozen=True)
class AppPaths:
    home: Path
    run_dir: Path
    socket_path: Path
    run_info_path: Path
    daemon_log_path: Path
    artifacts_dir: Path
    tasks_dir: Path
    automations_dir: Path
    automation_db_path: Path
    automation_service_run_info_path: Path
    automation_service_log_path: Path
    automation_service_host: str
    automation_service_port: int | None
    extension_host: str
    extension_port: int
    extension_ws_path: str


return AppPaths(
    home=home,
    run_dir=run_dir,
    socket_path=socket_path,
    run_info_path=run_dir / "daemon.json",
    daemon_log_path=run_dir / "daemon.log",
    artifacts_dir=home / "artifacts",
    tasks_dir=home / "tasks",
    automations_dir=home / "automations",
    automation_db_path=home / "automations.db",
    automation_service_run_info_path=run_dir / "automation-service.json",
    automation_service_log_path=run_dir / "automation-service.log",
    automation_service_host=automation_service_host,
    automation_service_port=automation_service_port,
    extension_host=extension_host,
    extension_port=extension_port,
    extension_ws_path="/ext",
)
```

- [ ] **Step 4: Replace the top-level parser groups in `main.py`**

```python
from browser_cli.commands.automation import run_automation_command
from browser_cli.commands.task import run_task_command


task_parser = subparsers.add_parser(
    "task",
    help="Run or validate a local task directory.",
    description="Run task.py + task.meta.json from a local task directory.",
)
task_subparsers = task_parser.add_subparsers(dest="task_subcommand", metavar="TASK_COMMAND")

task_run_parser = task_subparsers.add_parser("run", help="Run a task directory.")
task_run_parser.add_argument("path", help="Path to the task directory.")
task_run_parser.add_argument("--set", dest="set_values", action="append", default=[])
task_run_parser.add_argument("--inputs-json")
task_run_parser.set_defaults(handler=run_task_command)

task_validate_parser = task_subparsers.add_parser("validate", help="Validate a task directory.")
task_validate_parser.add_argument("path", help="Path to the task directory.")
task_validate_parser.set_defaults(handler=run_task_command)

automation_parser = subparsers.add_parser(
    "automation",
    help="Publish and operate versioned automations.",
    description="Publish a task snapshot and manage automation service state.",
)
automation_subparsers = automation_parser.add_subparsers(
    dest="automation_subcommand", metavar="AUTOMATION_COMMAND"
)
```

- [ ] **Step 5: Run the parser/path tests to verify they pass**

Run: `pytest tests/unit/test_task_commands.py -k "parser_exposes_task_and_automation or app_paths_exposes_task_and_automation_roots" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/browser_cli/constants.py src/browser_cli/cli/main.py tests/unit/test_task_commands.py
git commit -m "feat: add task and automation parser skeleton"
```

### Task 2: Extract Shared Task Entrypoint Loading And Validation

**Files:**
- Create: `src/browser_cli/task_runtime/entrypoint.py`
- Modify: `src/browser_cli/task_runtime/models.py`
- Modify: `src/browser_cli/task_runtime/__init__.py`
- Test: `tests/unit/test_task_entrypoint.py`

- [ ] **Step 1: Write failing task-entrypoint tests**

```python
from pathlib import Path

import pytest

from browser_cli.task_runtime.entrypoint import (
    load_task_entrypoint,
    parse_input_overrides,
    run_task_entrypoint,
    validate_task_dir,
)


def test_validate_task_dir_rejects_missing_task_meta(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text("def run(flow, inputs):\n    return {}\n", encoding="utf-8")
    with pytest.raises(Exception, match="task.meta.json"):
        validate_task_dir(tmp_path)


def test_load_task_entrypoint_returns_callable(tmp_path: Path) -> None:
    (tmp_path / "task.py").write_text("def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8")
    (tmp_path / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    entrypoint = load_task_entrypoint(tmp_path / "task.py", "run")
    assert callable(entrypoint)


def test_parse_input_overrides_merges_json_and_set_values() -> None:
    payload = parse_input_overrides(["url=https://example.com"], '{"timeout": 5}')
    assert payload == {"timeout": 5, "url": "https://example.com"}
```

- [ ] **Step 2: Run the task-entrypoint tests to verify they fail**

Run: `pytest tests/unit/test_task_entrypoint.py -v`
Expected: FAIL because `browser_cli.task_runtime.entrypoint` does not exist.

- [ ] **Step 3: Add a reusable task-dir validator**

```python
from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
from typing import Any, Callable

from browser_cli.task_runtime.errors import TaskEntrypointError, TaskMetadataError
from browser_cli.task_runtime.models import validate_task_metadata


def validate_task_dir(task_dir: Path) -> dict[str, Any]:
    task_path = task_dir / "task.py"
    meta_path = task_dir / "task.meta.json"
    if not task_path.exists():
        raise TaskEntrypointError(f"Task directory is missing task.py: {task_dir}")
    if not meta_path.exists():
        raise TaskMetadataError(f"Task directory is missing task.meta.json: {task_dir}")
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    validate_task_metadata(payload, source=str(meta_path))
    load_task_entrypoint(task_path, "run")
    return payload
```

- [ ] **Step 4: Add module loading and entrypoint contract checks**

```python
def parse_input_overrides(pairs: list[str] | None, inputs_json: str | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if inputs_json:
        payload = json.loads(inputs_json)
        if not isinstance(payload, dict):
            raise TaskMetadataError("--inputs-json must decode to a JSON object.")
        merged.update(payload)
    for pair in pairs or []:
        if "=" not in pair:
            raise TaskMetadataError(f"Invalid --set value {pair!r}; expected KEY=VALUE.")
        key, value = pair.split("=", 1)
        merged[key] = value
    return merged


def load_task_entrypoint(task_path: Path, entrypoint: str) -> Callable[..., dict[str, Any]]:
    spec = importlib.util.spec_from_file_location(f"browser_cli_task_{task_path.stem}", task_path)
    if spec is None or spec.loader is None:
        raise TaskEntrypointError(f"Could not load task module: {task_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, entrypoint, None)
    if fn is None or not callable(fn):
        raise TaskEntrypointError(
            f"Task entrypoint {entrypoint!r} is missing or not callable: {task_path}"
        )
    signature = inspect.signature(fn)
    positional = [
        param
        for param in signature.parameters.values()
        if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) < 2:
        raise TaskEntrypointError(
            f"Task entrypoint must accept flow and inputs parameters: {task_path}"
        )
    return fn


def run_task_entrypoint(
    *,
    task_path: Path,
    entrypoint: str,
    inputs: dict[str, Any],
    artifacts_dir: Path,
    automation_path: Path | None = None,
    automation_name: str | None = None,
    client: BrowserCliTaskClient | None = None,
    stdout_handle: Any | None = None,
    stderr_handle: Any | None = None,
) -> dict[str, Any]:
    fn = load_task_entrypoint(task_path, entrypoint)
    flow = Flow(
        client=client or BrowserCliTaskClient(),
        context=FlowContext(
            task_path=task_path,
            task_dir=task_path.parent,
            artifacts_dir=artifacts_dir,
            automation_path=automation_path,
            automation_name=automation_name,
        ),
    )
    result = fn(flow, inputs)
    if not isinstance(result, dict):
        raise TaskEntrypointError(f"Task entrypoint must return a dict: {task_path}")
    return result
```

- [ ] **Step 5: Export the new helpers from `task_runtime.__init__`**

```python
from browser_cli.task_runtime.entrypoint import (
    load_task_entrypoint,
    parse_input_overrides,
    run_task_entrypoint,
    validate_task_dir,
)

__all__ = [
    "BrowserCliTaskClient",
    "Flow",
    "FlowContext",
    "SnapshotResult",
    "SnapshotRef",
    "load_task_entrypoint",
    "parse_input_overrides",
    "run_task_entrypoint",
    "validate_task_dir",
]
```

- [ ] **Step 6: Rename workflow-specific context fields in `task_runtime.models`**

```python
@dataclass(slots=True, frozen=True)
class FlowContext:
    task_path: Path
    task_dir: Path
    artifacts_dir: Path
    automation_path: Path | None = None
    automation_name: str | None = None
```

- [ ] **Step 7: Run the task-entrypoint tests to verify they pass**

Run: `pytest tests/unit/test_task_entrypoint.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/browser_cli/task_runtime/entrypoint.py src/browser_cli/task_runtime/models.py src/browser_cli/task_runtime/__init__.py tests/unit/test_task_entrypoint.py
git commit -m "feat: add reusable task entrypoint validation"
```

### Task 3: Implement `task run` And `task validate`

**Files:**
- Create: `src/browser_cli/commands/task.py`
- Modify: `src/browser_cli/task_runtime/models.py`
- Test: `tests/unit/test_task_commands.py`
- Test: `tests/integration/test_task_cli.py`

- [ ] **Step 1: Write failing command tests for `task run` and `task validate`**

```python
from argparse import Namespace
from pathlib import Path

from browser_cli.commands.task import run_task_command


def test_task_validate_returns_json_payload(tmp_path: Path) -> None:
    task_dir = tmp_path / "demo"
    task_dir.mkdir()
    (task_dir / "task.py").write_text("def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8")
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    payload = run_task_command(Namespace(task_subcommand="validate", path=str(task_dir)))
    assert '"valid": true' in payload.lower()


def test_task_run_executes_task_dir(monkeypatch, tmp_path: Path) -> None:
    task_dir = tmp_path / "demo"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'url': inputs['url'], 'ok': True}\n",
        encoding="utf-8",
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    payload = run_task_command(
        Namespace(
            task_subcommand="run",
            path=str(task_dir),
            set_values=["url=https://example.com"],
            inputs_json=None,
        )
    )
    assert '"ok": true' in payload.lower()
```

- [ ] **Step 2: Run the command tests to verify they fail**

Run: `pytest tests/unit/test_task_commands.py -k "task_validate_returns_json_payload or task_run_executes_task_dir" -v`
Expected: FAIL because `browser_cli.commands.task` does not exist.

- [ ] **Step 3: Implement input parsing and validation response in `commands/task.py`**

```python
from argparse import Namespace
from pathlib import Path

from browser_cli.outputs.json import render_json_payload
from browser_cli.task_runtime import parse_input_overrides, run_task_entrypoint, validate_task_dir


def run_task_command(args: Namespace) -> str:
    task_dir = Path(args.path).expanduser().resolve()
    if args.task_subcommand == "validate":
        metadata = validate_task_dir(task_dir)
        return render_json_payload(
            {
                "ok": True,
                "data": {
                    "valid": True,
                    "task": {
                        "path": str(task_dir / "task.py"),
                        "meta_path": str(task_dir / "task.meta.json"),
                        "id": str(metadata["task"]["id"]),
                    },
                },
                "meta": {"action": "task-validate"},
            }
        )
    result = run_task_entrypoint(
        task_path=task_dir / "task.py",
        entrypoint="run",
        inputs=parse_input_overrides(getattr(args, "set_values", None), getattr(args, "inputs_json", None)),
        artifacts_dir=task_dir / "artifacts",
    )
    return render_json_payload({"ok": True, "data": result, "meta": {"action": "task-run"}})
```

- [ ] **Step 4: Implement `task run` on top of `Flow` and shared task loading**

```python
from browser_cli.task_runtime import parse_input_overrides, run_task_entrypoint


def _run_task(task_dir: Path, input_overrides: dict[str, object]) -> dict[str, object]:
    return run_task_entrypoint(
        task_path=task_dir / "task.py",
        entrypoint="run",
        inputs=input_overrides,
        artifacts_dir=task_dir / "artifacts",
    )
```

- [ ] **Step 5: Add an integration test that exercises the public CLI**

```python
from browser_cli.cli.main import main


def test_task_validate_and_run_against_local_fixture(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    task_dir = tmp_path / "fixture_task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text(
        "def run(flow, inputs):\n    return {'url': inputs['url'], 'ok': True}\n",
        encoding="utf-8",
    )
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"fixture","name":"Fixture","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    assert main(["task", "validate", str(task_dir)]) == 0
    assert main(["task", "run", str(task_dir), "--set", "url=https://example.com"]) == 0
```

- [ ] **Step 6: Run unit and integration tests to verify they pass**

Run: `pytest tests/unit/test_task_commands.py tests/integration/test_task_cli.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/browser_cli/commands/task.py src/browser_cli/task_runtime/models.py tests/unit/test_task_commands.py tests/integration/test_task_cli.py
git commit -m "feat: add task run and validate commands"
```

### Task 4: Add Automation Models, Loader, And Snapshot Publisher

**Files:**
- Create: `src/browser_cli/automation/models.py`
- Create: `src/browser_cli/automation/loader.py`
- Create: `src/browser_cli/automation/publisher.py`
- Create: `src/browser_cli/automation/__init__.py`
- Test: `tests/unit/test_automation_loader.py`
- Test: `tests/unit/test_automation_publish.py`

- [ ] **Step 1: Write failing tests for `automation.toml` and snapshot publishing**

```python
from pathlib import Path

from browser_cli.automation.loader import load_automation_manifest
from browser_cli.automation.publisher import publish_task_dir


def test_load_automation_manifest_resolves_snapshot_files(tmp_path: Path) -> None:
    manifest_path = tmp_path / "automation.toml"
    manifest_path.write_text(
        "[automation]\n"
        'id = "demo"\n'
        'name = "Demo"\n'
        "[task]\n"
        'path = "task.py"\n'
        'meta_path = "task.meta.json"\n',
        encoding="utf-8",
    )
    (tmp_path / "task.py").write_text("def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8")
    (tmp_path / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    manifest = load_automation_manifest(manifest_path)
    assert manifest.automation.id == "demo"
    assert manifest.task.path == tmp_path / "task.py"


def test_publish_task_dir_creates_versioned_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "home"))
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text("def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8")
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    published = publish_task_dir(task_dir, app_paths=get_app_paths())
    assert published.automation_id == "demo"
    assert published.version == 1
    assert (published.snapshot_dir / "automation.toml").exists()
```

- [ ] **Step 2: Run the automation loader/publisher tests to verify they fail**

Run: `pytest tests/unit/test_automation_loader.py tests/unit/test_automation_publish.py -v`
Expected: FAIL because `browser_cli.automation` does not exist.

- [ ] **Step 3: Define manifest and persistence dataclasses in `automation/models.py`**

```python
@dataclass(slots=True, frozen=True)
class AutomationIdentity:
    id: str
    name: str
    description: str = ""
    version: str = "1"


@dataclass(slots=True, frozen=True)
class AutomationTaskConfig:
    path: Path
    meta_path: Path
    entrypoint: str = "run"


@dataclass(slots=True, frozen=True)
class AutomationManifest:
    manifest_path: Path
    automation: AutomationIdentity
    task: AutomationTaskConfig
    inputs: dict[str, Any] = field(default_factory=dict)
    schedule: dict[str, Any] = field(default_factory=dict)
    outputs: AutomationOutputs = field(default_factory=lambda: AutomationOutputs(artifact_dir=Path("runs")))
    hooks: AutomationHooks = field(default_factory=AutomationHooks)
    runtime: AutomationRuntime = field(default_factory=AutomationRuntime)
```

- [ ] **Step 4: Implement `automation.toml` loading and validation**

```python
def load_automation_manifest(path: str | Path) -> AutomationManifest:
    manifest_path = Path(path).expanduser().resolve()
    data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    automation_section = _require_section(data, "automation", manifest_path)
    task_section = _require_section(data, "task", manifest_path)
    task_path = _resolve_relative(manifest_path.parent, _require_string(task_section, "path", manifest_path))
    meta_path = _resolve_relative(manifest_path.parent, _require_string(task_section, "meta_path", manifest_path))
    validate_task_metadata(json.loads(meta_path.read_text(encoding="utf-8")), source=str(meta_path))
    return AutomationManifest(
        manifest_path=manifest_path,
        automation=AutomationIdentity(
            id=_require_string(automation_section, "id", manifest_path),
            name=_require_string(automation_section, "name", manifest_path),
            description=str(automation_section.get("description") or ""),
            version=str(automation_section.get("version") or "1"),
        ),
        task=AutomationTaskConfig(path=task_path, meta_path=meta_path, entrypoint=str(task_section.get("entrypoint") or "run")),
    )
```

- [ ] **Step 5: Implement versioned snapshot publication**

```python
def publish_task_dir(task_dir: Path, *, app_paths: AppPaths) -> PublishedAutomation:
    metadata = validate_task_dir(task_dir)
    automation_id = str(metadata["task"]["id"])
    versions_dir = app_paths.automations_dir / automation_id / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    version = _next_version(versions_dir)
    snapshot_dir = versions_dir / str(version)
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(task_dir / "task.py", snapshot_dir / "task.py")
    shutil.copy2(task_dir / "task.meta.json", snapshot_dir / "task.meta.json")
    manifest_path = snapshot_dir / "automation.toml"
    manifest_path.write_text(
        render_automation_manifest(
            automation_id=automation_id,
            name=str(metadata["task"]["name"]),
            version=version,
            task_path=snapshot_dir / "task.py",
            task_meta_path=snapshot_dir / "task.meta.json",
        ),
        encoding="utf-8",
    )
    (snapshot_dir / "publish.json").write_text(
        json.dumps(
            {
                "automation_id": automation_id,
                "version": version,
                "source_task_path": str(task_dir),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return PublishedAutomation(automation_id=automation_id, version=version, snapshot_dir=snapshot_dir, manifest_path=manifest_path)
```

- [ ] **Step 6: Run loader/publisher tests to verify they pass**

Run: `pytest tests/unit/test_automation_loader.py tests/unit/test_automation_publish.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/browser_cli/automation/__init__.py src/browser_cli/automation/models.py src/browser_cli/automation/loader.py src/browser_cli/automation/publisher.py tests/unit/test_automation_loader.py tests/unit/test_automation_publish.py
git commit -m "feat: add automation manifest and snapshot publisher"
```

### Task 5: Replace Workflow Persistence And Runtime With Automation Service

**Files:**
- Create: `src/browser_cli/automation/persistence/store.py`
- Create: `src/browser_cli/automation/persistence/__init__.py`
- Create: `src/browser_cli/automation/service/runtime.py`
- Create: `src/browser_cli/automation/service/client.py`
- Create: `src/browser_cli/automation/service/__main__.py`
- Create: `src/browser_cli/automation/service/__init__.py`
- Modify: `src/browser_cli/constants.py`
- Test: `tests/unit/test_automation_service.py`

- [ ] **Step 1: Write failing persistence/runtime tests**

```python
from pathlib import Path

from browser_cli.automation.models import PersistedAutomationDefinition
from browser_cli.automation.persistence import AutomationStore


def test_store_upserts_automation_versions_and_runs(tmp_path: Path) -> None:
    store = AutomationStore(tmp_path / "automations.db")
    automation = PersistedAutomationDefinition(
        id="demo",
        version=1,
        name="Demo",
        snapshot_dir=tmp_path / "automations" / "demo" / "versions" / "1",
        task_path=tmp_path / "automations" / "demo" / "versions" / "1" / "task.py",
        task_meta_path=tmp_path / "automations" / "demo" / "versions" / "1" / "task.meta.json",
    )
    created = store.upsert_automation(automation)
    assert created.id == "demo"
    assert created.version == 1
```

- [ ] **Step 2: Run the persistence/runtime tests to verify they fail**

Run: `pytest tests/unit/test_automation_service.py -v`
Expected: FAIL because `AutomationStore` and automation service modules do not exist.

- [ ] **Step 3: Define persistence models with stable id and version**

```python
@dataclass(slots=True, frozen=True)
class PersistedAutomationDefinition:
    id: str
    version: int
    name: str
    description: str = ""
    snapshot_dir: Path = Path()
    task_path: Path = Path()
    task_meta_path: Path = Path()
    manifest_path: Path = Path()
    enabled: bool = False
    schedule_kind: str = "manual"
    schedule_payload: dict[str, Any] = field(default_factory=dict)
    timezone: str = "UTC"
    output_dir: Path = Path()
    result_json_path: Path | None = None
    input_overrides: dict[str, Any] = field(default_factory=dict)
    before_run_hooks: tuple[str, ...] = ()
    after_success_hooks: tuple[str, ...] = ()
    after_failure_hooks: tuple[str, ...] = ()
    retry_attempts: int = 0
    timeout_seconds: float | None = None
```

- [ ] **Step 4: Create SQLite tables for automations, versions, runs, and events**

```sql
CREATE TABLE IF NOT EXISTS automations (
    id TEXT PRIMARY KEY,
    current_version INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 0,
    schedule_kind TEXT NOT NULL DEFAULT 'manual',
    schedule_payload_json TEXT NOT NULL DEFAULT '{}',
    timezone TEXT NOT NULL DEFAULT 'UTC',
    output_dir TEXT NOT NULL,
    result_json_path TEXT,
    input_overrides_json TEXT NOT NULL DEFAULT '{}',
    before_run_hooks_json TEXT NOT NULL DEFAULT '[]',
    after_success_hooks_json TEXT NOT NULL DEFAULT '[]',
    after_failure_hooks_json TEXT NOT NULL DEFAULT '[]',
    retry_attempts INTEGER NOT NULL DEFAULT 0,
    timeout_seconds REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    next_run_at TEXT
);
CREATE TABLE IF NOT EXISTS automation_versions (
    automation_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    snapshot_dir TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    task_path TEXT NOT NULL,
    task_meta_path TEXT NOT NULL,
    published_at TEXT NOT NULL,
    PRIMARY KEY (automation_id, version)
);
```

- [ ] **Step 5: Port the runtime executor to load snapshot tasks**

```python
result = run_task_entrypoint(
    task_path=version.task_path,
    entrypoint="run",
    inputs=run.effective_inputs,
    artifacts_dir=run_dir,
    automation_path=version.manifest_path,
    automation_name=automation.name,
    client=BrowserCliTaskClient(),
    stdout_handle=log_handle,
    stderr_handle=log_handle,
)
```

- [ ] **Step 6: Update service client helpers to use automation-specific run-info and API roots**

```python
def automation_service_ui_url() -> str:
    run_info = read_automation_service_run_info()
    if run_info and run_info.get("host") and run_info.get("port"):
        return f"http://{run_info['host']}:{run_info['port']}/"
    paths = get_app_paths()
    host = paths.automation_service_host
    port = paths.automation_service_port or DEFAULT_AUTOMATION_SERVICE_PORT
    return f"http://{host}:{port}/"
```

- [ ] **Step 7: Run automation service tests to verify they pass**

Run: `pytest tests/unit/test_automation_service.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/browser_cli/automation/persistence/__init__.py src/browser_cli/automation/persistence/store.py src/browser_cli/automation/service/__init__.py src/browser_cli/automation/service/client.py src/browser_cli/automation/service/runtime.py src/browser_cli/automation/service/__main__.py src/browser_cli/constants.py tests/unit/test_automation_service.py
git commit -m "feat: add automation persistence and runtime service"
```

### Task 6: Implement Automation CLI, API, Export/Import, And Status Wiring

**Files:**
- Create: `src/browser_cli/commands/automation.py`
- Create: `src/browser_cli/automation/api/server.py`
- Create: `src/browser_cli/automation/api/__init__.py`
- Create: `src/browser_cli/automation/web/assets.py`
- Create: `src/browser_cli/automation/web/__init__.py`
- Modify: `src/browser_cli/commands/status.py`
- Test: `tests/unit/test_automation_api.py`
- Test: `tests/integration/test_automation_cli.py`

- [ ] **Step 1: Write failing CLI/API tests for publish, export, UI, and status**

```python
from browser_cli.cli.main import main


def test_automation_publish_returns_id_and_version(capsys, monkeypatch, tmp_path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.py").write_text("def run(flow, inputs):\n    return {'ok': True}\n", encoding="utf-8")
    (task_dir / "task.meta.json").write_text(
        '{"task":{"id":"demo","name":"Demo","goal":"Run"},"environment":{},"success_path":{},"recovery_hints":{},"failures":[],"knowledge":{}}',
        encoding="utf-8",
    )
    payload = _run_cli_json(["automation", "publish", str(task_dir)], capsys)
    assert payload["data"]["published"]["automation_id"] == "demo"
    assert payload["data"]["published"]["version"] == 1


def test_automation_api_export_returns_automation_toml(tmp_path):
    runtime = AutomationServiceRuntime(store=AutomationStore(tmp_path / "automations.db"))
    server = AutomationHttpServer(("127.0.0.1", 0), AutomationRequestHandler, runtime)
    with _serve(server):
        create_payload = _request(
            server.server_address[0],
            int(server.server_address[1]),
            "POST",
            "/api/automations",
            {"id": "demo", "name": "Demo", "version": 1, "snapshot_dir": str(tmp_path / "versions" / "1")},
        )
        assert create_payload["data"]["id"] == "demo"
        export_payload = _request(
            server.server_address[0],
            int(server.server_address[1]),
            "GET",
            "/api/automations/demo/export",
        )
        assert "[automation]" in export_payload["data"]["toml"]
```

- [ ] **Step 2: Run the CLI/API tests to verify they fail**

Run: `pytest tests/unit/test_automation_api.py tests/integration/test_automation_cli.py -v`
Expected: FAIL because the automation command handler and API server do not exist.

- [ ] **Step 3: Implement `automation publish` and service-management commands**

```python
def run_automation_command(args: Namespace) -> str:
    subcommand = args.automation_subcommand
    if subcommand == "publish":
        published = publish_task_dir(Path(args.path).expanduser().resolve(), app_paths=get_app_paths())
        ensure_automation_service_running()
        payload = request_automation_service(
            "POST",
            "/api/automations/import",
            body={"path": str(published.manifest_path), "enabled": True},
            start_if_needed=False,
        )
        payload["meta"] = {"action": "automation-publish"}
        payload["data"]["published"] = {
            "automation_id": published.automation_id,
            "version": published.version,
            "snapshot_dir": str(published.snapshot_dir),
        }
        return render_json_payload(payload)
```

- [ ] **Step 4: Port the HTTP API from `/api/workflows` to `/api/automations`**

```python
if path == "/api/automations" and method == "GET":
    automations = [
        self._serialize_automation(item, include_latest_run=True)
        for item in self.server.runtime.store.list_automations()
    ]
    self._send_json({"ok": True, "data": automations, "meta": {}})

if path == "/api/automations/import" and method == "POST":
    manifest = load_automation_manifest(str(body["path"]))
    automation = manifest_to_persisted_definition(manifest, enabled=enabled)
    created = self.server.runtime.store.upsert_automation(automation)
    self._send_json({"ok": True, "data": self._serialize_automation(created), "meta": {}})
```

- [ ] **Step 5: Update the status command to report automation service health**

```python
automation_run_info = read_automation_service_run_info()
automation_service_section = {
    "running": bool(automation_run_info),
    "pid": _int_or_none((automation_run_info or {}).get("pid")),
    "url": (
        f"http://{automation_run_info['host']}:{automation_run_info['port']}/"
        if automation_run_info and automation_run_info.get("host") and automation_run_info.get("port")
        else None
    ),
    "automation_count": 0,
    "queued_runs": 0,
    "running_runs": 0,
}
```

- [ ] **Step 6: Rewrite the web UI copy and field names around automations**

```html
<h1>Browser CLI Automations</h1>
<p>Published automation snapshots managed by the local automation service.</p>
<div id="automation-list"></div>
<h2>Automation Detail</h2>
```

- [ ] **Step 7: Run the CLI/API/status tests to verify they pass**

Run: `pytest tests/unit/test_automation_api.py tests/integration/test_automation_cli.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/browser_cli/commands/automation.py src/browser_cli/automation/api/__init__.py src/browser_cli/automation/api/server.py src/browser_cli/automation/web/__init__.py src/browser_cli/automation/web/assets.py src/browser_cli/commands/status.py tests/unit/test_automation_api.py tests/integration/test_automation_cli.py
git commit -m "feat: add automation command surface and service api"
```

### Task 7: Remove Legacy Workflow Surface And Port Example Fixtures

**Files:**
- Delete: `src/browser_cli/commands/workflow.py`
- Delete: `src/browser_cli/workflow/`
- Modify: `tasks/interactive_reveal_capture/automation.toml`
- Modify: `tasks/lazy_scroll_capture/automation.toml`
- Delete: `tasks/interactive_reveal_capture/workflow.toml`
- Delete: `tasks/lazy_scroll_capture/workflow.toml`
- Modify: `tests/unit/test_python_compatibility.py`

- [ ] **Step 1: Write failing fixture and compatibility tests against the new file names**

```python
def test_lazy_scroll_automation_manifest_exists() -> None:
    manifest_path = REPO_ROOT / "tasks" / "lazy_scroll_capture" / "automation.toml"
    payload = manifest_path.read_text(encoding="utf-8")
    assert "[automation]" in payload


def test_automation_modules_import_on_current_python() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import browser_cli.automation.api.server; "
            "import browser_cli.automation.persistence.store; "
            "import browser_cli.automation.service.runtime",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
```

- [ ] **Step 2: Run the fixture and compatibility tests to verify they fail**

Run: `pytest tests/unit/test_python_compatibility.py tests/unit/test_automation_loader.py -v`
Expected: FAIL because example manifests still use `workflow.toml` and workflow imports remain.

- [ ] **Step 3: Rename the example manifests and update their sections**

```toml
[automation]
id = "interactive_reveal_capture"
name = "Interactive Reveal Capture"
description = "Capture revealed content after a semantic click."
version = "1"

[task]
path = "task.py"
meta_path = "task.meta.json"
entrypoint = "run"
```

- [ ] **Step 4: Remove the legacy workflow command and package tree**

```bash
rm -rf src/browser_cli/workflow
rm -f src/browser_cli/commands/workflow.py
rm -f tasks/interactive_reveal_capture/workflow.toml tasks/lazy_scroll_capture/workflow.toml
```

- [ ] **Step 5: Update imports and compatibility tests to the automation package**

```python
from browser_cli.automation.api import AutomationHttpServer, AutomationRequestHandler
from browser_cli.automation.persistence import AutomationStore
from browser_cli.automation.service.runtime import AutomationServiceRuntime
```

- [ ] **Step 6: Run the renamed-fixture and compatibility tests to verify they pass**

Run: `pytest tests/unit/test_python_compatibility.py tests/unit/test_automation_loader.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tasks/interactive_reveal_capture/automation.toml tasks/lazy_scroll_capture/automation.toml tests/unit/test_python_compatibility.py
git rm -r src/browser_cli/workflow src/browser_cli/commands/workflow.py tasks/interactive_reveal_capture/workflow.toml tasks/lazy_scroll_capture/workflow.toml
git commit -m "refactor: remove legacy workflow surface"
```

### Task 8: Update Skill, Docs, Guards, And AGENTS Guidance

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `skills/browser-cli-explore-delivery/SKILL.md`
- Modify: `skills/browser-cli-explore-delivery/references/preflight-and-runtime.md`
- Modify: `docs/smoke-checklist.md`
- Create: `docs/examples/task-and-automation.md`
- Delete: `docs/examples/task-and-workflow.md`
- Modify: `scripts/guards/product_contracts.py`
- Modify: `scripts/guards/architecture.py`
- Modify: `scripts/guards/docs_sync.py`

- [ ] **Step 1: Write failing guard tests for the new top-level command contract**

```python
def _check_task_contract(parser: argparse.ArgumentParser) -> list[Finding]:
    expected = {"run", "validate"}
    actual = set(_subcommand_parsers(parser))
    if actual != expected:
        return [
            Finding(
                "error",
                "CONTRACT006",
                f"'task' subcommands changed unexpectedly. Expected {sorted(expected)}, found {sorted(actual)}.",
            )
        ]
    return []


def _check_automation_contract(parser: argparse.ArgumentParser) -> list[Finding]:
    expected = {"export", "import", "publish", "status", "stop", "ui"}
    actual = set(_subcommand_parsers(parser))
    if actual != expected:
        return [
            Finding(
                "error",
                "CONTRACT007",
                f"'automation' subcommands changed unexpectedly. Expected {sorted(expected)}, found {sorted(actual)}.",
            )
        ]
    return []
```

- [ ] **Step 2: Run the guard suite to verify it fails**

Run: `python scripts/guards/run_all.py`
Expected: FAIL because `product_contracts.py`, `architecture.py`, and docs still reference `workflow`.

- [ ] **Step 3: Rewrite `README.md` and `AGENTS.md` around task and automation**

````markdown
## Task & Automation Packaging

```text
~/.browser-cli/tasks/my_task/
  task.py
  task.meta.json

~/.browser-cli/automations/my_task/
  versions/1/automation.toml
```

### Run Tasks

```bash
browser-cli task validate ~/.browser-cli/tasks/my_task
browser-cli task run ~/.browser-cli/tasks/my_task --set url=https://example.com
browser-cli automation publish ~/.browser-cli/tasks/my_task
browser-cli automation ui
```
````

- [ ] **Step 4: Strengthen the skill with canonical templates and validation**

````markdown
## 4. Converge to `task.py`

- `task.py` must expose `run(flow, inputs) -> dict`
- start from the canonical task template below
- after writing `task.py` and `task.meta.json`, run `browser-cli task validate <task-dir>`

### Canonical `task.py` template

```python
from browser_cli.task_runtime import Flow


def run(flow: Flow, inputs: dict) -> dict:
    raise NotImplementedError
```
````

- [ ] **Step 5: Update guards and architecture boundaries**

```python
ALLOWED_DEPENDENCIES: dict[str, set[str]] = {
    "commands": {"automation", "daemon", "errors", "outputs", "runtime"},
    "automation": {"errors", "task_runtime", "automation"},
    "task_runtime": {"daemon", "errors", "task_runtime"},
}

if "task" not in top_level_commands:
    findings.append(Finding("error", "CONTRACT003", "Top-level 'task' command is required."))
if "automation" not in top_level_commands:
    findings.append(Finding("error", "CONTRACT004", "Top-level 'automation' command is required."))
```

- [ ] **Step 6: Run lint, guards, and doc-sensitive tests to verify they pass**

Run: `./scripts/lint.sh && python scripts/guards/run_all.py && pytest tests/unit/test_task_commands.py tests/unit/test_automation_api.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add README.md AGENTS.md skills/browser-cli-explore-delivery/SKILL.md skills/browser-cli-explore-delivery/references/preflight-and-runtime.md docs/smoke-checklist.md docs/examples/task-and-automation.md scripts/guards/product_contracts.py scripts/guards/architecture.py scripts/guards/docs_sync.py
git rm docs/examples/task-and-workflow.md
git commit -m "docs: update task and automation guidance"
```

### Task 9: Run Full Validation And Clean Up Residual Workflow References

**Files:**
- Modify: any remaining files returned by `rg -n "workflow" src tests README.md AGENTS.md skills docs scripts -S`
- Test: full repository validation

- [ ] **Step 1: Search for residual public `workflow` references**

Run: `rg -n "workflow" src tests README.md AGENTS.md skills docs scripts -S`
Expected: only historical spec references and internal migration notes remain; no public CLI, public docs, public tests, or runtime code should still present `workflow` as a live surface.

- [ ] **Step 2: Remove or rewrite any remaining live-surface references**

```python
class AutomationServiceNotAvailableError(BrowserCliError):
    def __init__(self, message: str = "Automation service is not available.") -> None:
        super().__init__(message, exit_codes.TEMPORARY_FAILURE, error_codes.AUTOMATION_SERVICE_NOT_AVAILABLE)
```

- [ ] **Step 3: Run unit and integration tests**

Run: `./scripts/test.sh`
Expected: PASS

- [ ] **Step 4: Run lint and guards**

Run: `./scripts/lint.sh && ./scripts/guard.sh`
Expected: PASS

- [ ] **Step 5: Run the full repository check**

Run: `./scripts/check.sh`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: finalize task and automation cutover"
```

## Spec Coverage Check

- Public `task` CLI surface: covered by Tasks 1 and 3.
- Public `automation` CLI surface: covered by Tasks 1, 4, 5, and 6.
- Task validation contract: covered by Tasks 2 and 3.
- Snapshot-based publish flow: covered by Tasks 4, 5, and 6.
- Stable automation id plus versioning: covered by Tasks 4 and 5.
- Service execution from snapshots, not source tasks: covered by Task 5.
- Removal of `workflow` public naming: covered by Tasks 1, 6, 7, 8, and 9.
- Skill template enforcement and docs updates: covered by Task 8.
- Guard, AGENTS, and README synchronization: covered by Task 8.
- Full validation: covered by Task 9.

## Placeholder Scan

- No `TODO`, `TBD`, or deferred placeholders were left in the tasks.
- Each code-edit step includes concrete file paths and code to add or replace.
- Each verification step includes an exact command and expected result.

## Type Consistency Check

- Public nouns are consistently `task`, `automation`, and `run`.
- Persisted objects use `automation_id` and integer `version`.
- Published manifests use `automation.toml` and `[automation]`.
- Validation helpers are centralized in `browser_cli.task_runtime.entrypoint`.
