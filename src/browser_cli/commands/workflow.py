"""Workflow CLI commands."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from browser_cli.errors import WorkflowServiceNotAvailableError
from browser_cli.outputs.json import render_json_payload
from browser_cli.workflow.loader import load_workflow_manifest
from browser_cli.workflow.runner import parse_input_overrides, run_workflow
from browser_cli.workflow.service.client import (
    ensure_workflow_service_running,
    read_workflow_service_run_info,
    request_workflow_service,
    stop_workflow_service,
    workflow_service_ui_url,
)


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
    if subcommand == "ui":
        url = workflow_service_ui_url()
        return render_json_payload(
            {
                "ok": True,
                "data": {"url": url, "run_info": read_workflow_service_run_info()},
                "meta": {"action": "workflow-ui"},
            }
        )
    if subcommand == "service-status":
        run_info = read_workflow_service_run_info()
        if not run_info:
            payload = {
                "ok": True,
                "data": {"running": False},
                "meta": {"action": "workflow-service-status"},
            }
            return render_json_payload(payload)
        try:
            payload = request_workflow_service("GET", "/api/service/status", start_if_needed=False)
        except WorkflowServiceNotAvailableError:
            return render_json_payload(
                {
                    "ok": True,
                    "data": {"running": False, "stale_run_info": run_info},
                    "meta": {"action": "workflow-service-status"},
                }
            )
        payload["data"]["run_info"] = run_info
        payload["meta"] = {"action": "workflow-service-status"}
        return render_json_payload(payload)
    if subcommand == "service-stop":
        return render_json_payload(
            {
                "ok": True,
                "data": stop_workflow_service(),
                "meta": {"action": "workflow-service-stop"},
            }
        )
    if subcommand == "import":
        ensure_workflow_service_running()
        payload = request_workflow_service(
            "POST",
            "/api/workflows/import",
            body={"path": args.path, "enabled": bool(getattr(args, "enable", False))},
            start_if_needed=False,
        )
        payload["meta"] = {"action": "workflow-import"}
        return render_json_payload(payload)
    if subcommand == "export":
        payload = request_workflow_service(
            "GET",
            f"/api/workflows/{args.workflow_id}/export",
            start_if_needed=True,
        )
        toml_text = str((payload.get("data") or {}).get("toml") or "")
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(toml_text, encoding="utf-8")
        return render_json_payload(
            {
                "ok": True,
                "data": {"workflow_id": args.workflow_id, "output": str(output_path)},
                "meta": {"action": "workflow-export"},
            }
        )

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
