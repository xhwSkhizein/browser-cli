"""Runtime paths and shared constants."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

APP_HOME_ENV = "BROWSER_CLI_HOME"
DEFAULT_HOME_DIRNAME = ".browser-cli"
DEFAULT_PUBLIC_AGENT_ID = "public"
EXTENSION_HOST_ENV = "BROWSER_CLI_EXTENSION_HOST"
EXTENSION_PORT_ENV = "BROWSER_CLI_EXTENSION_PORT"
DEFAULT_EXTENSION_HOST = "127.0.0.1"
DEFAULT_EXTENSION_PORT = 19825
WORKFLOW_SERVICE_HOST_ENV = "BROWSER_CLI_WORKFLOW_HOST"
WORKFLOW_SERVICE_PORT_ENV = "BROWSER_CLI_WORKFLOW_PORT"
DEFAULT_WORKFLOW_SERVICE_HOST = "127.0.0.1"


@dataclass(slots=True, frozen=True)
class AppPaths:
    home: Path
    run_dir: Path
    socket_path: Path
    run_info_path: Path
    daemon_log_path: Path
    artifacts_dir: Path
    workflow_db_path: Path
    workflow_runs_dir: Path
    workflow_service_run_info_path: Path
    workflow_service_log_path: Path
    workflow_service_host: str
    workflow_service_port: int | None
    extension_host: str
    extension_port: int
    extension_ws_path: str

    @property
    def extension_ws_url(self) -> str:
        return f"ws://{self.extension_host}:{self.extension_port}{self.extension_ws_path}"


def get_app_paths() -> AppPaths:
    configured_home = os.environ.get(APP_HOME_ENV)
    home = (
        Path(configured_home).expanduser()
        if configured_home
        else Path.home() / DEFAULT_HOME_DIRNAME
    )
    run_dir = home / "run"
    socket_path = run_dir / "browser-cli.sock"
    if len(str(socket_path)) > 90:
        digest = hashlib.sha1(str(home).encode("utf-8")).hexdigest()[:12]
        socket_path = Path(tempfile.gettempdir()) / f"browser-cli-{digest}.sock"
    workflow_service_host = (
        os.environ.get(WORKFLOW_SERVICE_HOST_ENV, DEFAULT_WORKFLOW_SERVICE_HOST).strip()
        or DEFAULT_WORKFLOW_SERVICE_HOST
    )
    raw_workflow_service_port = os.environ.get(WORKFLOW_SERVICE_PORT_ENV, "").strip()
    workflow_service_port: int | None = None
    if raw_workflow_service_port:
        try:
            workflow_service_port = int(raw_workflow_service_port)
        except ValueError:
            workflow_service_port = None
    extension_host = (
        os.environ.get(EXTENSION_HOST_ENV, DEFAULT_EXTENSION_HOST).strip() or DEFAULT_EXTENSION_HOST
    )
    raw_extension_port = os.environ.get(EXTENSION_PORT_ENV, str(DEFAULT_EXTENSION_PORT)).strip()
    try:
        extension_port = int(raw_extension_port)
    except ValueError:
        extension_port = DEFAULT_EXTENSION_PORT
    return AppPaths(
        home=home,
        run_dir=run_dir,
        socket_path=socket_path,
        run_info_path=run_dir / "daemon.json",
        daemon_log_path=run_dir / "daemon.log",
        artifacts_dir=home / "artifacts",
        workflow_db_path=home / "workflows.db",
        workflow_runs_dir=home / "workflows",
        workflow_service_run_info_path=run_dir / "workflow-service.json",
        workflow_service_log_path=run_dir / "workflow-service.log",
        workflow_service_host=workflow_service_host,
        workflow_service_port=workflow_service_port,
        extension_host=extension_host,
        extension_port=extension_port,
        extension_ws_path="/ext",
    )
