"""In-memory daemon command run registry."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from browser_cli.errors import BrowserCliError

ReadHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
BeginHandler = Callable[[str], Awaitable[None]]
EndHandler = Callable[[], Awaitable[dict[str, Any]]]

MAX_COMPLETED_RUNS = 100
TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}


class CommandRunRegistry:
    def __init__(
        self,
        *,
        read_handler: ReadHandler,
        begin_handler: BeginHandler | None = None,
        end_handler: EndHandler | None = None,
        max_completed_runs: int = MAX_COMPLETED_RUNS,
    ) -> None:
        self._read_handler = read_handler
        self._begin_handler = begin_handler
        self._end_handler = end_handler
        self._max_completed_runs = max_completed_runs
        self._counter = 0
        self._runs: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start_read(self, args: dict[str, Any]) -> dict[str, Any]:
        self._counter += 1
        run_id = f"run_{self._counter:06d}"
        record = {
            "run_id": run_id,
            "command": "read",
            "status": "queued",
            "created_at": time.time(),
            "updated_at": time.time(),
            "args": dict(args),
            "events": [],
            "result": None,
            "error": None,
            "meta": None,
        }
        self._runs[run_id] = record
        self._event(record, "queued", "Read run queued.")
        self._tasks[run_id] = asyncio.create_task(self._execute_read(run_id))
        self._evict_completed_runs()
        return self.status(run_id)

    def status(self, run_id: str) -> dict[str, Any]:
        record = self._runs.get(run_id)
        if record is None:
            return {"run_id": run_id, "status": "not_found", "message": "Run id was not found."}
        return {
            "run_id": record["run_id"],
            "command": record["command"],
            "status": record["status"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "result": record["result"],
            "error": record["error"],
            "meta": record["meta"],
        }

    def logs(self, run_id: str, *, tail: int = 200) -> dict[str, Any]:
        record = self._runs.get(run_id)
        if record is None:
            return {"run_id": run_id, "status": "not_found", "events": []}
        events = [] if tail <= 0 else list(record["events"])[-tail:]
        return {"run_id": run_id, "status": record["status"], "events": events}

    def cancel(self, run_id: str) -> dict[str, Any]:
        record = self._runs.get(run_id)
        if record is None:
            return {"run_id": run_id, "status": "not_found", "cancel_requested": False}
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            record["status"] = "cancel_requested"
            self._event(record, "cancel_requested", "Cancellation requested.")
            task.cancel()
            return {"run_id": run_id, "status": "cancel_requested", "cancel_requested": True}
        return {"run_id": run_id, "status": record["status"], "cancel_requested": False}

    async def wait_for_idle(self) -> None:
        tasks = list(self._tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_read(self, run_id: str) -> None:
        record = self._runs[run_id]
        command_started = False
        try:
            record["status"] = "running"
            self._event(record, "started", "Read run started.")
            if self._begin_handler is not None:
                await self._begin_handler("read-async")
                command_started = True
            result = await self._read_handler(dict(record["args"]))
            record["status"] = "succeeded"
            record["result"] = dict(result)
            self._event(record, "completed", "Read run completed.")
        except asyncio.CancelledError:
            record["status"] = "canceled"
            self._event(record, "canceled", "Read run canceled.")
            raise
        except BrowserCliError as exc:
            record["status"] = "failed"
            record["error"] = {
                "error_code": exc.error_code,
                "message": exc.message,
                "type": type(exc).__name__,
            }
            self._event(record, "failed", exc.message)
        except Exception as exc:  # pragma: no cover - last-resort run guard
            record["status"] = "failed"
            record["error"] = {"message": str(exc), "type": type(exc).__name__}
            self._event(record, "failed", str(exc))
        finally:
            if command_started and self._end_handler is not None:
                try:
                    record["meta"] = await self._end_handler()
                except Exception as exc:  # pragma: no cover - last-resort cleanup guard
                    record["error"] = {"message": str(exc), "type": type(exc).__name__}
                    if record["status"] == "succeeded":
                        record["status"] = "failed"
                    self._event(record, "failed", f"Command cleanup failed: {exc}")
            record["updated_at"] = time.time()
            self._evict_completed_runs()

    def _event(self, record: dict[str, Any], event: str, message: str) -> None:
        now = time.time()
        record["updated_at"] = now
        record["events"].append({"at": now, "event": event, "message": message})

    def _evict_completed_runs(self) -> None:
        if len(self._runs) <= self._max_completed_runs:
            return
        evictable = [
            record
            for record in self._runs.values()
            if record["status"] in TERMINAL_STATUSES and not self._task_is_active(record["run_id"])
        ]
        evictable.sort(key=lambda record: float(record["created_at"]))
        for record in evictable:
            if len(self._runs) <= self._max_completed_runs:
                return
            run_id = str(record["run_id"])
            self._event(record, "evicted", "Run evicted from memory.")
            task = self._tasks.pop(run_id, None)
            if task is not None and not task.done():
                task.cancel()
            self._runs.pop(run_id, None)

    def _task_is_active(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()
