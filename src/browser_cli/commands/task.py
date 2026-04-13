"""Task CLI commands."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from browser_cli.errors import InvalidInputError
from browser_cli.outputs.json import render_json_payload
from browser_cli.task_runtime import parse_input_overrides, run_task_entrypoint, validate_task_dir
from browser_cli.task_runtime.templates import (
    EXAMPLE_CATALOG,
    TASK_TEMPLATE_FILES,
    render_template_bundle,
)


def run_task_command(args: Namespace) -> str:
    if args.task_subcommand == "examples":
        return "\n".join(f"{name}: {summary}" for name, summary in EXAMPLE_CATALOG) + "\n"

    if args.task_subcommand == "template":
        output = getattr(args, "output", None)
        if output:
            output_dir = Path(output).expanduser().resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            for name, body in TASK_TEMPLATE_FILES.items():
                (output_dir / name).write_text(body, encoding="utf-8")
            return f"Template written to {output_dir}\n"
        return render_template_bundle()

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

    if args.task_subcommand == "run":
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

    raise InvalidInputError(f"Unsupported task subcommand: {args.task_subcommand}")
