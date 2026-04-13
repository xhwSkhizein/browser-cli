"""Automation CLI commands."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from browser_cli.automation import load_automation_manifest, publish_task_dir
from browser_cli.automation.service.client import (
    automation_service_ui_url,
    ensure_automation_service_running,
    read_automation_service_run_info,
    request_automation_service,
    stop_automation_service,
)
from browser_cli.constants import get_app_paths
from browser_cli.outputs.json import render_json_payload


def run_automation_command(args: Namespace) -> str:
    subcommand = args.automation_subcommand
    if subcommand == "publish":
        published = publish_task_dir(
            Path(args.path).expanduser().resolve(), app_paths=get_app_paths()
        )
        ensure_automation_service_running()
        payload = request_automation_service(
            "POST",
            "/api/automations/import",
            body={
                "path": str(published.manifest_path),
                "enabled": True,
            },
            start_if_needed=False,
        )
        return render_json_payload(
            {
                "ok": True,
                "data": {
                    "published": {
                        "automation_id": published.automation_id,
                        "automation_name": published.automation_name,
                        "version": published.version,
                        "snapshot_dir": str(published.snapshot_dir),
                        "manifest_path": str(published.manifest_path),
                    },
                    "service": payload.get("data") or {},
                },
                "meta": {"action": "automation-publish"},
            }
        )
    if subcommand == "import":
        ensure_automation_service_running()
        manifest = load_automation_manifest(args.path)
        payload = request_automation_service(
            "POST",
            "/api/automations",
            body=_manifest_to_automation_payload(
                manifest, enabled=bool(getattr(args, "enable", False))
            ),
            start_if_needed=False,
        )
        payload["meta"] = {"action": "automation-import"}
        return render_json_payload(payload)
    if subcommand == "export":
        payload = request_automation_service(
            "GET",
            f"/api/automations/{args.automation_id}/export",
            start_if_needed=True,
        )
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(str((payload.get("data") or {}).get("toml") or ""), encoding="utf-8")
        return render_json_payload(
            {
                "ok": True,
                "data": {"automation_id": args.automation_id, "output": str(output_path)},
                "meta": {"action": "automation-export"},
            }
        )
    if subcommand == "ui":
        return render_json_payload(
            {
                "ok": True,
                "data": {
                    "url": automation_service_ui_url(),
                    "run_info": read_automation_service_run_info(),
                },
                "meta": {"action": "automation-ui"},
            }
        )
    if subcommand == "status":
        run_info = read_automation_service_run_info()
        if not run_info:
            return render_json_payload(
                {
                    "ok": True,
                    "data": {"running": False},
                    "meta": {"action": "automation-status"},
                }
            )
        payload = request_automation_service("GET", "/api/service/status", start_if_needed=False)
        payload["meta"] = {"action": "automation-status"}
        return render_json_payload(payload)
    if subcommand == "stop":
        return render_json_payload(
            {
                "ok": True,
                "data": stop_automation_service(),
                "meta": {"action": "automation-stop"},
            }
        )
    raise ValueError(f"Unsupported automation subcommand: {subcommand}")


def _manifest_to_automation_payload(manifest, *, enabled: bool) -> dict[str, object]:
    schedule = dict(manifest.schedule)
    return {
        "id": manifest.automation.id,
        "name": manifest.automation.name,
        "description": manifest.automation.description,
        "version": manifest.automation.version,
        "task_path": str(manifest.task.path),
        "task_meta_path": str(manifest.task.meta_path),
        "entrypoint": manifest.task.entrypoint,
        "enabled": enabled,
        "schedule_kind": str(schedule.get("mode") or "manual"),
        "schedule_payload": schedule,
        "timezone": str(schedule.get("timezone") or "UTC"),
        "output_dir": str(manifest.outputs.artifact_dir),
        "result_json_path": str(manifest.outputs.result_json_path or ""),
        "input_overrides": dict(manifest.inputs),
        "before_run_hooks": list(manifest.hooks.before_run),
        "after_success_hooks": list(manifest.hooks.after_success),
        "after_failure_hooks": list(manifest.hooks.after_failure),
        "retry_attempts": int(manifest.runtime.retry_attempts or 0),
        "timeout_seconds": manifest.runtime.timeout_seconds,
    }
