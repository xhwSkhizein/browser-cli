"""Automation service runtime."""

from __future__ import annotations

import json
import logging
import multiprocessing
import threading
import time
from pathlib import Path
from typing import Any

from browser_cli import __version__, error_codes
from browser_cli.automation.hooks import run_hook_commands
from browser_cli.automation.models import AutomationRunEvent
from browser_cli.automation.persistence import AutomationStore
from browser_cli.constants import get_app_paths
from browser_cli.errors import AutomationRunTimeoutError, OperationFailedError
from browser_cli.task_runtime import run_task_entrypoint
from browser_cli.task_runtime.client import BrowserCliTaskClient

logger = logging.getLogger(__name__)

AUTOMATION_SERVICE_RUNTIME_VERSION = "2026-04-12-automation-service-v1"
FAILURE_HOOK_TIMEOUT_SECONDS = 5.0


def _run_task_entrypoint_child(
    queue,
    *,
    task_path: str,
    entrypoint: str,
    inputs: dict[str, Any],
    artifacts_dir: str,
    automation_path: str | None,
    automation_name: str | None,
    log_path: str,
) -> None:
    try:
        with open(log_path, "a", encoding="utf-8") as log_handle:
            result = run_task_entrypoint(
                task_path=Path(task_path),
                entrypoint=entrypoint,
                inputs=inputs,
                artifacts_dir=Path(artifacts_dir),
                automation_path=Path(automation_path) if automation_path else None,
                automation_name=automation_name,
                client=BrowserCliTaskClient(),
                stdout_handle=log_handle,
                stderr_handle=log_handle,
            )
        queue.put({"ok": True, "result": result})
    except BaseException as exc:  # noqa: BLE001
        queue.put(
            {
                "ok": False,
                "error_message": str(exc),
                "error_code": (
                    exc.error_code
                    if isinstance(exc, OperationFailedError)
                    else error_codes.AUTOMATION_RUN_FAILED
                ),
            }
        )


class AutomationServiceRuntime:
    def __init__(self, store: AutomationStore | None = None) -> None:
        self.app_paths = get_app_paths()
        self.store = store or AutomationStore()
        self.started_at = time.time()
        self.stop_event = threading.Event()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="automation-service-scheduler",
            daemon=True,
        )
        self._executor_thread = threading.Thread(
            target=self._executor_loop,
            name="automation-service-executor",
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
                "runtime_version": AUTOMATION_SERVICE_RUNTIME_VERSION,
                "package_version": __version__,
                "db_path": str(self.store.db_path),
                "runs_dir": str(self.app_paths.automation_runs_dir),
            },
            "metrics": metrics,
        }

    def _scheduler_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.store.enqueue_due_runs()
            except Exception:
                logger.exception("Automation scheduler loop failed")
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
                logger.exception("Automation executor loop failed")
                self.stop_event.wait(0.5)

    def _execute_run(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        automation = self.store.get_automation(run.automation_id)
        run_dir = (automation.output_dir / "runs" / run.run_id).resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "run.log"
        result_path = run_dir / "result.json"
        deadline = self._deadline_for_run(automation.timeout_seconds)
        stage = "daemon_ready"
        self.store.add_run_event(
            run_id,
            AutomationRunEvent(
                run_id=run_id,
                event_type="task_started",
                message="Task execution started.",
            ),
        )
        try:
            client = BrowserCliTaskClient()
            self._run_with_timeout(
                lambda: client.command("runtime-status"),
                timeout_seconds=self._remaining_timeout(deadline, stage="daemon_ready"),
                timeout_message=(
                    f"Automation run timed out during daemon readiness after "
                    f"{automation.timeout_seconds} seconds."
                ),
            )
            self.store.add_run_event(
                run_id,
                AutomationRunEvent(
                    run_id=run_id,
                    event_type="browser_daemon_ready",
                    message="Browser daemon is reachable.",
                ),
            )
        except Exception as exc:
            self.store.add_run_event(
                run_id,
                AutomationRunEvent(
                    run_id=run_id,
                    event_type="browser_daemon_unavailable",
                    message=str(exc),
                ),
            )

        with log_path.open("a", encoding="utf-8") as log_handle:
            try:
                hook_env = {
                    "BROWSER_CLI_AUTOMATION_ID": automation.id,
                    "BROWSER_CLI_AUTOMATION_NAME": automation.name,
                    "BROWSER_CLI_TASK_PATH": str(automation.task_path),
                    "BROWSER_CLI_AUTOMATION_STATUS": "running",
                }
                stage = "before_hooks"
                before_hooks = run_hook_commands(
                    automation.before_run_hooks,
                    cwd=automation.task_path.parent,
                    extra_env=hook_env,
                    timeout_seconds=self._remaining_timeout(deadline, stage=stage),
                )
                if before_hooks:
                    log_handle.write(
                        json.dumps({"before_hooks": before_hooks}, ensure_ascii=False) + "\n"
                    )
                stage = "task_execution"
                result = self._run_task_entrypoint_with_timeout(
                    task_path=automation.task_path,
                    entrypoint=automation.entrypoint,
                    inputs=run.effective_inputs,
                    artifacts_dir=run_dir,
                    automation_path=automation.output_dir,
                    automation_name=automation.name,
                    log_path=log_path,
                    timeout_seconds=self._remaining_timeout(deadline, stage=stage),
                )
                stage = "persist_result"
                self._ensure_time_remaining(deadline, stage=stage)
                result_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                if automation.result_json_path is not None:
                    self._ensure_time_remaining(deadline, stage=stage)
                    automation.result_json_path.parent.mkdir(parents=True, exist_ok=True)
                    automation.result_json_path.write_text(
                        json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                stage = "after_success_hooks"
                success_hooks = run_hook_commands(
                    automation.after_success_hooks,
                    cwd=automation.task_path.parent,
                    extra_env={**hook_env, "BROWSER_CLI_AUTOMATION_STATUS": "success"},
                    timeout_seconds=self._remaining_timeout(deadline, stage=stage),
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
                timed_out = isinstance(exc, AutomationRunTimeoutError)
                if timed_out:
                    self.store.add_run_event(
                        run_id,
                        AutomationRunEvent(
                            run_id=run_id,
                            event_type="run_timed_out",
                            message=str(exc),
                            payload={"stage": stage},
                        ),
                    )
                try:
                    failure_hooks = run_hook_commands(
                        automation.after_failure_hooks,
                        cwd=automation.task_path.parent,
                        extra_env={
                            "BROWSER_CLI_AUTOMATION_ID": automation.id,
                            "BROWSER_CLI_AUTOMATION_NAME": automation.name,
                            "BROWSER_CLI_TASK_PATH": str(automation.task_path),
                            "BROWSER_CLI_AUTOMATION_STATUS": "failure",
                        },
                        timeout_seconds=FAILURE_HOOK_TIMEOUT_SECONDS,
                    )
                    if failure_hooks:
                        log_handle.write(
                            json.dumps({"after_failure_hooks": failure_hooks}, ensure_ascii=False)
                            + "\n"
                        )
                except Exception:
                    logger.exception("Automation failure hooks failed for %s", automation.id)
                logger.exception("Automation run failed: %s", run_id)
                log_handle.write(f"\nERROR: {exc}\n")
                error_code = (
                    exc.error_code
                    if isinstance(exc, OperationFailedError)
                    else error_codes.AUTOMATION_RUN_FAILED
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
                if not timed_out and automation.retry_attempts > run.attempt_number:
                    retry_run = self.store.retry_run(run_id)
                    self.store.add_run_event(
                        retry_run.run_id,
                        AutomationRunEvent(
                            run_id=retry_run.run_id,
                            event_type="retry_scheduled",
                            message=f"Retry scheduled after failed run {run_id}.",
                        ),
                    )

    @staticmethod
    def _deadline_for_run(timeout_seconds: float | None) -> float | None:
        if timeout_seconds is None or timeout_seconds <= 0:
            return None
        return time.monotonic() + timeout_seconds

    @staticmethod
    def _remaining_timeout(deadline: float | None, *, stage: str) -> float | None:
        if deadline is None:
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AutomationRunTimeoutError(
                f"Automation run timed out during {stage} before work could continue."
            )
        return remaining

    @staticmethod
    def _ensure_time_remaining(deadline: float | None, *, stage: str) -> None:
        _ = AutomationServiceRuntime._remaining_timeout(deadline, stage=stage)

    @staticmethod
    def _run_with_timeout(
        fn,
        *,
        timeout_seconds: float | None,
        timeout_message: str,
    ):
        if timeout_seconds is None:
            return fn()
        result_box: dict[str, Any] = {}
        error_box: dict[str, BaseException] = {}

        def _target() -> None:
            try:
                result_box["value"] = fn()
            except BaseException as exc:  # noqa: BLE001
                error_box["error"] = exc

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        thread.join(timeout=timeout_seconds)
        if thread.is_alive():
            raise AutomationRunTimeoutError(timeout_message)
        if "error" in error_box:
            raise error_box["error"]
        return result_box.get("value")

    @staticmethod
    def _run_task_entrypoint_with_timeout(
        *,
        task_path: Path,
        entrypoint: str,
        inputs: dict[str, Any],
        artifacts_dir: Path,
        automation_path: Path | None,
        automation_name: str | None,
        log_path: Path,
        timeout_seconds: float | None,
    ) -> dict[str, Any]:
        if timeout_seconds is None:
            timeout_seconds = None
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        process = context.Process(
            target=_run_task_entrypoint_child,
            kwargs={
                "queue": queue,
                "task_path": str(task_path),
                "entrypoint": entrypoint,
                "inputs": inputs,
                "artifacts_dir": str(artifacts_dir),
                "automation_path": str(automation_path) if automation_path else None,
                "automation_name": automation_name,
                "log_path": str(log_path),
            },
            daemon=True,
        )
        process.start()
        process.join(timeout=timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1.0)
            raise AutomationRunTimeoutError(
                f"Automation run timed out during task execution after {timeout_seconds} seconds."
            )
        if queue.empty():
            raise OperationFailedError("Task worker exited without returning a result.")
        payload = queue.get()
        if bool(payload.get("ok")):
            return dict(payload.get("result") or {})
        raise OperationFailedError(
            str(payload.get("error_message") or "Task worker failed."),
            error_code=str(payload.get("error_code") or error_codes.AUTOMATION_RUN_FAILED),
        )
