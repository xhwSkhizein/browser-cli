"""In-memory daemon command run registry."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from browser_cli.errors import BrowserCliError

ReadHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class CommandRunRegistry:
    def __init__(self, *, read_handler: ReadHandler) -> None:
        self._read_handler = read_handler
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
        }
        self._runs[run_id] = record
        self._event(record, "queued", "Read run queued.")
        self._tasks[run_id] = asyncio.create_task(self._execute_read(run_id))
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
        }

    def logs(self, run_id: str, *, tail: int = 200) -> dict[str, Any]:
        record = self._runs.get(run_id)
        if record is None:
            return {"run_id": run_id, "status": "not_found", "events": []}
        events = list(record["events"])[-max(0, tail) :]
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
        try:
            record["status"] = "running"
            self._event(record, "started", "Read run started.")
            result = await self._read_handler(dict(record["args"]))
            record["status"] = "succeeded"
            record["result"] = dict(result)
            self._event(record, "completed", "Read run completed.")
        except asyncio.CancelledError:
            record["status"] = "canceled"
            self._event(record, "canceled", "Read run canceled.")
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
            record["updated_at"] = time.time()

    def _event(self, record: dict[str, Any], event: str, message: str) -> None:
        now = time.time()
        record["updated_at"] = now
        record["events"].append({"at": now, "event": event, "message": message})
