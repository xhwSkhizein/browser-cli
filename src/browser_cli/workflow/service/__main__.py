"""Workflow service process entrypoint."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from browser_cli import __version__
from browser_cli.constants import APP_HOME_ENV, get_app_paths
from browser_cli.workflow.api import WorkflowHttpServer, WorkflowRequestHandler
from browser_cli.workflow.service.client import (
    _write_workflow_service_run_info,
    remove_workflow_service_run_info,
)
from browser_cli.workflow.service.runtime import (
    WORKFLOW_SERVICE_RUNTIME_VERSION,
    WorkflowServiceRuntime,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="browser-cli workflow-service")
    parser.add_argument("--home", help="Override Browser CLI home.")
    args = parser.parse_args(argv)
    if args.home:
        os.environ[APP_HOME_ENV] = str(Path(args.home).expanduser())
    logging.basicConfig(level=logging.INFO)
    runtime = WorkflowServiceRuntime()
    runtime.start()
    app_paths = get_app_paths()
    server = WorkflowHttpServer(
        (app_paths.workflow_service_host, app_paths.workflow_service_port or 0),
        WorkflowRequestHandler,
        runtime,
    )
    host, port = server.server_address[:2]
    _write_workflow_service_run_info(
        {
            "pid": os.getpid(),
            "host": host,
            "port": port,
            "started_at": runtime.started_at,
            "package_version": __version__,
            "runtime_version": WORKFLOW_SERVICE_RUNTIME_VERSION,
        }
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        runtime.stop()
        runtime.join(timeout=2.0)
        server.server_close()
        remove_workflow_service_run_info()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
