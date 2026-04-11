"""Workflow CLI commands."""

from __future__ import annotations

from argparse import Namespace

from browser_cli.outputs.json import render_json_payload
from browser_cli.workflow.loader import load_workflow_manifest
from browser_cli.workflow.runner import parse_input_overrides, run_workflow


def run_workflow_command(args: Namespace) -> str:
    subcommand = args.workflow_subcommand
    if subcommand == "validate":
        manifest = load_workflow_manifest(args.path)
        payload = {
            "ok": True,
            "data": {
                "valid": True,
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
            },
            "meta": {"action": "workflow-validate"},
        }
        return render_json_payload(payload)

    payload = {
        "ok": True,
        "data": run_workflow(
            args.path,
            input_overrides=parse_input_overrides(
                getattr(args, "set_values", None),
                getattr(args, "inputs_json", None),
            ),
        ),
        "meta": {"action": "workflow-run"},
    }
    return render_json_payload(payload)
