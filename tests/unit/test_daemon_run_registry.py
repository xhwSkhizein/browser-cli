from __future__ import annotations

import asyncio

from browser_cli.daemon.run_registry import CommandRunRegistry


def test_run_registry_completes_successful_read() -> None:
    async def _run() -> None:
        async def _read(args: dict[str, object]) -> dict[str, object]:
            assert args["url"] == "https://example.com"
            return {"body": "ok", "used_fallback_profile": False}

        registry = CommandRunRegistry(read_handler=_read)
        started = registry.start_read(
            {
                "url": "https://example.com",
                "output_mode": "html",
                "scroll_bottom": False,
            }
        )
        assert started["status"] == "queued"
        run_id = str(started["run_id"])
        await asyncio.sleep(0)
        status = registry.status(run_id)
        assert status["status"] in {"running", "succeeded"}
        await registry.wait_for_idle()
        status = registry.status(run_id)
        assert status["status"] == "succeeded"
        assert status["result"]["body"] == "ok"
        assert registry.logs(run_id, tail=10)["events"][-1]["event"] == "completed"

    asyncio.run(_run())


def test_run_registry_brackets_read_with_begin_and_end() -> None:
    async def _run() -> None:
        calls: list[str] = []

        async def _begin(command: str) -> None:
            calls.append(f"begin:{command}")

        async def _end() -> dict[str, object]:
            calls.append("end")
            return {"driver": "extension"}

        async def _read(args: dict[str, object]) -> dict[str, object]:
            _ = args
            calls.append("read")
            return {"body": "ok"}

        registry = CommandRunRegistry(
            read_handler=_read,
            begin_handler=_begin,
            end_handler=_end,
        )
        run_id = str(registry.start_read({"url": "https://example.com"})["run_id"])
        await registry.wait_for_idle()

        assert calls == ["begin:read-async", "read", "end"]
        assert registry.status(run_id)["meta"] == {"driver": "extension"}

    asyncio.run(_run())


def test_run_registry_cancel_marks_run() -> None:
    async def _run() -> None:
        started_event = asyncio.Event()

        async def _read(args: dict[str, object]) -> dict[str, object]:
            _ = args
            started_event.set()
            await asyncio.sleep(60)
            return {"body": "late"}

        registry = CommandRunRegistry(read_handler=_read)
        run_id = str(registry.start_read({"url": "https://example.com"})["run_id"])
        await started_event.wait()
        cancel = registry.cancel(run_id)
        assert cancel["cancel_requested"] is True
        await registry.wait_for_idle()
        assert registry.status(run_id)["status"] == "canceled"
        assert registry._tasks[run_id].cancelled() is True  # noqa: SLF001

    asyncio.run(_run())


def test_run_registry_logs_non_positive_tail_is_empty() -> None:
    async def _run() -> None:
        async def _read(args: dict[str, object]) -> dict[str, object]:
            _ = args
            return {"body": "ok"}

        registry = CommandRunRegistry(read_handler=_read)
        run_id = str(registry.start_read({"url": "https://example.com"})["run_id"])
        await registry.wait_for_idle()

        assert registry.logs(run_id, tail=0)["events"] == []
        assert registry.logs(run_id, tail=-1)["events"] == []
        assert len(registry.logs(run_id, tail=1)["events"]) == 1

    asyncio.run(_run())


def test_run_registry_evicts_old_completed_runs() -> None:
    async def _run() -> None:
        async def _read(args: dict[str, object]) -> dict[str, object]:
            return {"body": str(args["url"])}

        registry = CommandRunRegistry(read_handler=_read, max_completed_runs=2)
        first = str(registry.start_read({"url": "first"})["run_id"])
        await registry.wait_for_idle()
        second = str(registry.start_read({"url": "second"})["run_id"])
        await registry.wait_for_idle()
        third = str(registry.start_read({"url": "third"})["run_id"])
        await registry.wait_for_idle()

        assert registry.status(first)["status"] == "not_found"
        assert registry.status(second)["status"] == "succeeded"
        assert registry.status(third)["status"] == "succeeded"

    asyncio.run(_run())


def test_run_registry_not_found() -> None:
    async def _read(args: dict[str, object]) -> dict[str, object]:
        _ = args
        return {}

    registry = CommandRunRegistry(read_handler=_read)
    assert registry.status("run_missing")["status"] == "not_found"
