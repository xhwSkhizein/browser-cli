"""Automation CLI commands."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from browser_cli.automation import load_automation_manifest, publish_task_dir
from browser_cli.automation.models import AutomationManifest
from browser_cli.automation.service.client import (
    automation_service_ui_url,
    ensure_automation_service_running,
    read_automation_service_run_info,
    request_automation_service,
    stop_automation_service,
)
from browser_cli.constants import get_app_paths
from browser_cli.errors import InvalidInputError
from browser_cli.outputs.json import render_json_payload


def run_automation_command(args: Namespace) -> str:
    subcommand = args.automation_subcommand
    if subcommand == "publish":
        source_task_dir = Path(args.path).expanduser().resolve()
        published = publish_task_dir(source_task_dir, app_paths=get_app_paths())
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
                        "manifest_source": published.manifest_source,
                        "source_task_dir": str(source_task_dir),
                        "snapshot_dir": str(published.snapshot_dir),
                        "manifest_path": str(published.manifest_path),
                    },
                    "service": payload.get("data") or {},
                    "next_commands": {
                        "inspect": f"browser-cli automation inspect {published.automation_id}",
                        "status": "browser-cli automation status",
                        "ui": "browser-cli automation ui",
                    },
                    "model": {
                        "task": "local editable source",
                        "automation": "published immutable snapshot",
                    },
                },
                "meta": {"action": "automation-publish"},
            }
        )
    if subcommand == "list":
        payload = request_automation_service("GET", "/api/automations", start_if_needed=True)
        return render_json_payload(
            {
                "ok": True,
                "data": {"automations": payload.get("data") or []},
                "meta": {"action": "automation-list"},
            }
        )
    if subcommand == "versions":
        versions = _load_snapshot_versions(args.automation_id)
        return render_json_payload(
            {
                "ok": True,
                "data": {"automation_id": args.automation_id, "versions": versions},
                "meta": {"action": "automation-versions"},
            }
        )
    if subcommand == "inspect":
        payload = request_automation_service(
            "GET", f"/api/automations/{args.automation_id}", start_if_needed=True
        )
        versions = _load_snapshot_versions(args.automation_id)
        selected = _select_snapshot_version(
            args.automation_id,
            versions,
            version=getattr(args, "version", None),
        )
        live_automation_data = dict(payload.get("data") or {})
        selected_automation_data, selected_latest_run = _selected_snapshot_payload(
            selected, fallback_automation=live_automation_data
        )
        return render_json_payload(
            {
                "ok": True,
                "data": {
                    "automation": selected_automation_data,
                    "versions": versions,
                    "selected_version": selected,
                    "latest_run": selected_latest_run,
                    "summary": _build_inspect_summary(
                        args.automation_id,
                        selected_automation_data,
                        versions,
                        selected,
                        selected_latest_run,
                    ),
                },
                "meta": {"action": "automation-inspect"},
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


def _load_snapshot_versions(automation_id: str) -> list[dict[str, object]]:
    versions_dir = get_app_paths().automations_dir / automation_id / "versions"
    if not versions_dir.exists():
        return []
    versions: list[dict[str, object]] = []
    for entry in sorted(versions_dir.iterdir(), key=_version_sort_key, reverse=True):
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        publish_path = entry / "publish.json"
        publish_data = _read_json_file(publish_path)
        snapshot_manifest = _load_snapshot_manifest(entry / "automation.toml")
        versions.append(
            {
                "version": int(entry.name),
                "snapshot_dir": str(entry),
                "publish": publish_data,
                "snapshot_automation": (
                    _snapshot_manifest_to_automation_payload(snapshot_manifest)
                    if snapshot_manifest is not None
                    else None
                ),
                "snapshot_latest_run": publish_data.get("latest_run")
                if isinstance(publish_data.get("latest_run"), dict)
                else None,
                "task_path": str(entry / "task.py"),
                "task_meta_path": str(entry / "task.meta.json"),
            }
        )
    return versions


def _select_snapshot_version(
    automation_id: str,
    versions: list[dict[str, object]],
    *,
    version: int | None,
) -> dict[str, object] | None:
    if version is None:
        return versions[0] if versions else None
    for item in versions:
        if item["version"] == version:
            return item
    raise InvalidInputError(f"Automation version not found for {automation_id}: {version}")


def _version_sort_key(path: Path) -> int:
    try:
        return int(path.name)
    except ValueError:
        return -1


def _read_json_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _build_inspect_summary(
    automation_id: str,
    automation_data: dict[str, object],
    versions: list[dict[str, object]],
    selected: dict[str, object] | None,
    latest_run: dict[str, object] | None,
) -> dict[str, object]:
    latest_run_status = None
    if isinstance(latest_run, dict):
        latest_run_status = latest_run.get("status")
    return {
        "automation_id": automation_id,
        "persisted_version": automation_data.get("version"),
        "available_versions": [item["version"] for item in versions],
        "selected_version": selected.get("version") if selected else None,
        "selected_snapshot_dir": selected.get("snapshot_dir") if selected else None,
        "selected_task_path": selected.get("task_path") if selected else None,
        "schedule_mode": automation_data.get("schedule_kind"),
        "latest_run_status": latest_run_status,
    }


def _selected_snapshot_payload(
    selected: dict[str, object] | None,
    *,
    fallback_automation: dict[str, object],
) -> tuple[dict[str, object], dict[str, object] | None]:
    if selected is None:
        latest_run = fallback_automation.get("latest_run")
        return fallback_automation, latest_run if isinstance(latest_run, dict) else None
    snapshot_automation = selected.get("snapshot_automation")
    snapshot_latest_run = selected.get("snapshot_latest_run")
    if isinstance(snapshot_automation, dict):
        latest_run = snapshot_latest_run if isinstance(snapshot_latest_run, dict) else None
        return snapshot_automation, latest_run
    latest_run = fallback_automation.get("latest_run")
    return fallback_automation, latest_run if isinstance(latest_run, dict) else None


def _load_snapshot_manifest(path: Path) -> AutomationManifest | None:
    if not path.exists():
        return None
    return load_automation_manifest(path)


def _snapshot_manifest_to_automation_payload(manifest: AutomationManifest) -> dict[str, object]:
    schedule = dict(manifest.schedule)
    return {
        "id": manifest.automation.id,
        "name": manifest.automation.name,
        "description": manifest.automation.description,
        "version": manifest.automation.version,
        "task_path": str(manifest.task.path),
        "task_meta_path": str(manifest.task.meta_path),
        "entrypoint": manifest.task.entrypoint,
        "enabled": None,
        "definition_status": "snapshot",
        "definition_error": None,
        "schedule_kind": str(schedule.get("mode") or "manual"),
        "schedule_payload": schedule,
        "timezone": str(schedule.get("timezone") or "UTC"),
        "output_dir": str(manifest.outputs.artifact_dir),
        "result_json_path": str(manifest.outputs.result_json_path)
        if manifest.outputs.result_json_path
        else None,
        "stdout_mode": manifest.outputs.stdout,
        "input_overrides": dict(manifest.inputs),
        "before_run_hooks": list(manifest.hooks.before_run),
        "after_success_hooks": list(manifest.hooks.after_success),
        "after_failure_hooks": list(manifest.hooks.after_failure),
        "retry_attempts": int(manifest.runtime.retry_attempts or 0),
        "retry_backoff_seconds": int(manifest.runtime.retry_backoff_seconds or 0),
        "timeout_seconds": manifest.runtime.timeout_seconds,
        "created_at": None,
        "updated_at": None,
        "last_run_at": None,
        "next_run_at": None,
        "latest_run": None,
    }


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
        "stdout_mode": manifest.outputs.stdout,
        "input_overrides": dict(manifest.inputs),
        "before_run_hooks": list(manifest.hooks.before_run),
        "after_success_hooks": list(manifest.hooks.after_success),
        "after_failure_hooks": list(manifest.hooks.after_failure),
        "retry_attempts": int(manifest.runtime.retry_attempts or 0),
        "retry_backoff_seconds": int(manifest.runtime.retry_backoff_seconds or 0),
        "timeout_seconds": manifest.runtime.timeout_seconds,
    }
