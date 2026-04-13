"""Filesystem path discovery command."""

from __future__ import annotations

from argparse import Namespace

from browser_cli.constants import get_app_paths
from browser_cli.outputs.json import render_json_payload


def _paths_payload() -> dict[str, str]:
    app_paths = get_app_paths()
    return {
        "home": str(app_paths.home),
        "tasks_dir": str(app_paths.tasks_dir),
        "automations_dir": str(app_paths.automations_dir),
        "artifacts_dir": str(app_paths.artifacts_dir),
        "daemon_log_path": str(app_paths.daemon_log_path),
        "automation_db_path": str(app_paths.automation_db_path),
        "automation_service_run_info_path": str(app_paths.automation_service_run_info_path),
        "automation_service_log_path": str(app_paths.automation_service_log_path),
    }


def run_paths_command(args: Namespace) -> str:
    payload = _paths_payload()
    if getattr(args, "json", False):
        return render_json_payload({"ok": True, "data": payload, "meta": {"action": "paths"}})
    lines = ["Paths", ""]
    lines.extend(f"{key}: {value}" for key, value in payload.items())
    return "\n".join(lines) + "\n"
