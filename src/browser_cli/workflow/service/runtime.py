"""Workflow service runtime."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from browser_cli import __version__, error_codes
from browser_cli.constants import get_app_paths
from browser_cli.errors import OperationFailedError
from browser_cli.task_runtime.client import BrowserCliTaskClient
from browser_cli.workflow.hooks import run_hook_commands
from browser_cli.workflow.models import WorkflowRunEvent
from browser_cli.workflow.persistence import WorkflowStore
from browser_cli.workflow.runner import run_task_entrypoint

logger = logging.getLogger(__name__)

WORKFLOW_SERVICE_RUNTIME_VERSION = "2026-04-12-workflow-service-v1"


class WorkflowServiceRuntime:
    def __init__(self, store: WorkflowStore | None = None) -> None:
        self.app_paths = get_app_paths()
        self.store = store or WorkflowStore()
        self.started_at = time.time()
        self.stop_event = threading.Event()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="workflow-service-scheduler",
            daemon=True,
        )
        self._executor_thread = threading.Thread(
            target=self._executor_loop,
            name="workflow-service-executor",
            daemon=True,
        )

    def start(self) -> None:
        self._scheduler_thread.start()
        self._executor_thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        self._scheduler_thread.join(timeout=timeout)
        self._executor_thread.join(timeout=timeout)

    def status_payload(self) -> dict[str, Any]:
        metrics = self.store.service_metrics()
        return {
            "service": {
                "healthy": not self.stop_event.is_set(),
                "started_at": self.started_at,
                "runtime_version": WORKFLOW_SERVICE_RUNTIME_VERSION,
                "package_version": __version__,
                "db_path": str(self.store.db_path),
                "runs_dir": str(self.app_paths.workflow_runs_dir),
            },
            "metrics": metrics,
        }

    def _scheduler_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.store.enqueue_due_runs()
            except Exception:
                logger.exception("Workflow scheduler loop failed")
            self.stop_event.wait(1.0)

    def _executor_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                run = self.store.claim_next_run()
                if run is None:
                    self.stop_event.wait(0.5)
                    continue
                self._execute_run(run.run_id)
            except Exception:
                logger.exception("Workflow executor loop failed")
                self.stop_event.wait(0.5)

    def _execute_run(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        workflow = self.store.get_workflow(run.workflow_id)
        run_dir = (workflow.output_dir / "runs" / run.run_id).resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "run.log"
        result_path = run_dir / "result.json"
        self.store.add_run_event(
            run_id,
            WorkflowRunEvent(
                run_id=run_id,
                event_type="task_started",
                message="Task execution started.",
            ),
        )
        try:
            client = BrowserCliTaskClient()
            client.command("runtime-status")
            self.store.add_run_event(
                run_id,
                WorkflowRunEvent(
                    run_id=run_id,
                    event_type="browser_daemon_ready",
                    message="Browser daemon is reachable.",
                ),
            )
        except Exception as exc:
            self.store.add_run_event(
                run_id,
                WorkflowRunEvent(
                    run_id=run_id,
                    event_type="browser_daemon_unavailable",
                    message=str(exc),
                ),
            )

        with log_path.open("a", encoding="utf-8") as log_handle:
            try:
                hook_env = {
                    "BROWSER_CLI_WORKFLOW_ID": workflow.id,
                    "BROWSER_CLI_WORKFLOW_NAME": workflow.name,
                    "BROWSER_CLI_TASK_PATH": str(workflow.task_path),
                    "BROWSER_CLI_WORKFLOW_STATUS": "running",
                }
                before_hooks = run_hook_commands(
                    workflow.before_run_hooks,
                    cwd=workflow.task_path.parent,
                    extra_env=hook_env,
                )
                if before_hooks:
                    log_handle.write(
                        json.dumps({"before_hooks": before_hooks}, ensure_ascii=False) + "\n"
                    )
                result = run_task_entrypoint(
                    task_path=workflow.task_path,
                    entrypoint=workflow.entrypoint,
                    inputs=run.effective_inputs,
                    artifacts_dir=run_dir,
                    workflow_name=workflow.name,
                    client=BrowserCliTaskClient(),
                    stdout_handle=log_handle,
                    stderr_handle=log_handle,
                )
                result_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                if workflow.result_json_path is not None:
                    workflow.result_json_path.parent.mkdir(parents=True, exist_ok=True)
                    workflow.result_json_path.write_text(
                        json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                success_hooks = run_hook_commands(
                    workflow.after_success_hooks,
                    cwd=workflow.task_path.parent,
                    extra_env={**hook_env, "BROWSER_CLI_WORKFLOW_STATUS": "success"},
                )
                if success_hooks:
                    log_handle.write(
                        json.dumps({"after_success_hooks": success_hooks}, ensure_ascii=False)
                        + "\n"
                    )
                self.store.complete_run(
                    run_id,
                    status="success",
                    result_json_path=result_path,
                    artifacts_dir=run_dir,
                    log_path=log_path,
                )
            except Exception as exc:
                try:
                    failure_hooks = run_hook_commands(
                        workflow.after_failure_hooks,
                        cwd=workflow.task_path.parent,
                        extra_env={
                            "BROWSER_CLI_WORKFLOW_ID": workflow.id,
                            "BROWSER_CLI_WORKFLOW_NAME": workflow.name,
                            "BROWSER_CLI_TASK_PATH": str(workflow.task_path),
                            "BROWSER_CLI_WORKFLOW_STATUS": "failure",
                        },
                    )
                    if failure_hooks:
                        log_handle.write(
                            json.dumps({"after_failure_hooks": failure_hooks}, ensure_ascii=False)
                            + "\n"
                        )
                except Exception:
                    logger.exception("Workflow failure hooks failed for %s", workflow.id)
                logger.exception("Workflow run failed: %s", run_id)
                log_handle.write(f"\nERROR: {exc}\n")
                error_code = (
                    exc.error_code
                    if isinstance(exc, OperationFailedError)
                    else error_codes.WORKFLOW_RUN_FAILED
                )
                self.store.complete_run(
                    run_id,
                    status="failed",
                    error_code=error_code,
                    error_message=str(exc),
                    result_json_path=result_path if result_path.exists() else None,
                    artifacts_dir=run_dir,
                    log_path=log_path,
                )
                if workflow.retry_attempts > run.attempt_number:
                    retry_run = self.store.retry_run(run_id)
                    self.store.add_run_event(
                        retry_run.run_id,
                        WorkflowRunEvent(
                            run_id=retry_run.run_id,
                            event_type="retry_scheduled",
                            message=f"Retry scheduled after failed run {run_id}.",
                        ),
                    )
