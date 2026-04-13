"""Task CLI commands."""

from __future__ import annotations

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
        inputs=parse_input_overrides(
            getattr(args, "set_values", None),
            getattr(args, "inputs_json", None),
        ),
        artifacts_dir=task_dir / "artifacts",
    )
    return render_json_payload({"ok": True, "data": result, "meta": {"action": "task-run"}})
