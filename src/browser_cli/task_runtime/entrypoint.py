"""Shared task loading, validation, and execution helpers."""

from __future__ import annotations

import importlib.util
import inspect
import json
from collections.abc import Callable
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from browser_cli.task_runtime.client import BrowserCliTaskClient
from browser_cli.task_runtime.errors import TaskEntrypointError, TaskMetadataError
from browser_cli.task_runtime.flow import Flow
from browser_cli.task_runtime.models import FlowContext, validate_task_metadata


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
        if param.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
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
    if stdout_handle is None and stderr_handle is None:
        result = fn(flow, inputs)
    else:
        stdout_ctx = redirect_stdout(stdout_handle) if stdout_handle is not None else nullcontext()
        stderr_ctx = redirect_stderr(stderr_handle) if stderr_handle is not None else nullcontext()
        with stdout_ctx, stderr_ctx:
            result = fn(flow, inputs)
    if not isinstance(result, dict):
        raise TaskEntrypointError(f"Task entrypoint must return a dict: {task_path}")
    return result
