"""Workflow execution over Browser CLI tasks."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from browser_cli.errors import InvalidInputError
from browser_cli.task_runtime import Flow, FlowContext
from browser_cli.task_runtime.client import BrowserCliTaskClient
from browser_cli.task_runtime.errors import TaskEntrypointError
from browser_cli.workflow.hooks import run_hook_commands
from browser_cli.workflow.loader import load_workflow_manifest


def parse_input_overrides(pairs: list[str] | None, inputs_json: str | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if inputs_json:
        payload = json.loads(inputs_json)
        if not isinstance(payload, dict):
            raise InvalidInputError("--inputs-json must decode to a JSON object.")
        merged.update(payload)
    for pair in pairs or []:
        if "=" not in pair:
            raise InvalidInputError(f"Invalid --set value {pair!r}; expected KEY=VALUE.")
        key, value = pair.split("=", 1)
        merged[key] = value
    return merged


def run_workflow(
    path: str | Path, *, input_overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    manifest = load_workflow_manifest(path)
    merged_inputs = dict(manifest.inputs)
    if input_overrides:
        merged_inputs.update(input_overrides)

    flow = Flow(
        client=BrowserCliTaskClient(),
        context=FlowContext(
            task_path=manifest.task.path,
            task_dir=manifest.task.path.parent,
            artifacts_dir=manifest.outputs.artifact_dir,
            workflow_path=manifest.manifest_path,
            workflow_name=manifest.workflow.name,
        ),
    )

    hook_env = {
        "BROWSER_CLI_WORKFLOW_ID": manifest.workflow.id,
        "BROWSER_CLI_WORKFLOW_NAME": manifest.workflow.name,
        "BROWSER_CLI_WORKFLOW_PATH": str(manifest.manifest_path),
        "BROWSER_CLI_TASK_PATH": str(manifest.task.path),
    }
    before_hooks = run_hook_commands(
        manifest.hooks.before_run, cwd=manifest.manifest_path.parent, extra_env=hook_env
    )
    try:
        result = _run_task_module(
            manifest.task.path,
            entrypoint=manifest.task.entrypoint,
            flow=flow,
            inputs=merged_inputs,
        )
    except Exception:
        run_hook_commands(
            manifest.hooks.after_failure,
            cwd=manifest.manifest_path.parent,
            extra_env={**hook_env, "BROWSER_CLI_WORKFLOW_STATUS": "failure"},
        )
        raise
    success_hooks = run_hook_commands(
        manifest.hooks.after_success,
        cwd=manifest.manifest_path.parent,
        extra_env={**hook_env, "BROWSER_CLI_WORKFLOW_STATUS": "success"},
    )

    written_result_path: str | None = None
    if manifest.outputs.result_json_path is not None:
        manifest.outputs.result_json_path.parent.mkdir(parents=True, exist_ok=True)
        manifest.outputs.result_json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written_result_path = str(manifest.outputs.result_json_path)

    return {
        "workflow": {
            "id": manifest.workflow.id,
            "name": manifest.workflow.name,
            "path": str(manifest.manifest_path),
        },
        "task": {
            "path": str(manifest.task.path),
            "meta_path": str(manifest.task.meta_path),
            "entrypoint": manifest.task.entrypoint,
        },
        "inputs": merged_inputs,
        "result": result,
        "artifacts_dir": str(manifest.outputs.artifact_dir),
        "result_json_path": written_result_path,
        "hooks": {
            "before_run": before_hooks,
            "after_success": success_hooks,
        },
    }


def _run_task_module(
    task_path: Path, *, entrypoint: str, flow: Flow, inputs: dict[str, Any]
) -> dict[str, Any]:
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
    result = fn(flow, inputs)
    if not isinstance(result, dict):
        raise TaskEntrypointError(f"Task entrypoint must return a dict: {task_path}")
    return result
