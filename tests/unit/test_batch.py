from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from browser_cli.actions import get_action_specs
from browser_cli.cli.main import build_parser
from browser_cli.daemon.app import BrowserDaemonApp
from browser_cli.daemon.models import DaemonRequest
from browser_cli.daemon.state import DaemonState
from browser_cli.daemon.transport import DAEMON_RUNTIME_VERSION
from browser_cli.errors import InvalidInputError


class Service:
    active_driver_name = "playwright"
    chrome_environment = None

    def __init__(self):
        self.read_page_from_args = AsyncMock()
        self.begin_command = AsyncMock()
        self.end_command = AsyncMock(return_value={"driver": "playwright"})
        self.closed = False

    @asynccontextmanager
    async def isolated_context(self, options, tabs):
        try:
            yield self
        finally:
            self.closed = True


def request(action="batch", args=None, agent="a"):
    return DaemonRequest(action, args or {}, agent, "request")


def app_with_steps():
    service = Service()
    app = BrowserDaemonApp(DaemonState(browser_service=service))
    seen = []

    async def step(req):
        seen.append(req.args.get("n"))
        if req.args.get("fail"):
            raise InvalidInputError("intentional step failure")
        return {"n": req.args.get("n")}

    app._handlers["eval"] = step
    return app, service, seen


@pytest.mark.parametrize("mode,indices", [("all", [0, 1, 2]), ("last", [2]), ("summary", [1])])
def test_batch_orders_actions_and_preserves_errors_with_compact_results(mode, indices):
    app, _, seen = app_with_steps()
    commands = [{"action": "eval", "args": {"n": i, "fail": i == 1}} for i in range(3)]
    response = asyncio.run(
        app.execute(
            request(args={"commands": commands, "stop_on_error": False, "result_mode": mode})
        )
    )
    assert response.ok
    assert seen == [0, 1, 2]
    assert response.data["success"] is False
    assert response.data["failed_indices"] == [1]
    assert response.data["completed_count"] == 3
    assert [step["index"] for step in response.data["results"]] == indices
    if mode != "last":
        error = next(step for step in response.data["results"] if step["index"] == 1)
        assert error["error_code"] == "INVALID_INPUT"
        assert error["meta"]["agent_id"] == "a"


def test_batch_stops_after_failure_by_default():
    app, _, seen = app_with_steps()
    response = asyncio.run(
        app.execute(
            request(
                args={
                    "commands": [
                        {"action": "eval", "args": {"n": 0, "fail": True}},
                        {"action": "eval", "args": {"n": 1}},
                    ]
                }
            )
        )
    )
    assert seen == [0]
    assert response.data["completed"] is False


@pytest.mark.parametrize(
    "extra",
    [
        {"commands": []},
        {"commands": [{"action": "batch"}]},
        {"commands": [{"action": "stop"}]},
        {"commands": [{"action": "bad"}]},
        {"commands": [{"action": "eval", "args": []}]},
        {"result_mode": []},
        {"stop_on_error": "yes"},
        {"context": {"device_scale_factor": 0}},
    ],
)
def test_batch_validates_before_running_any_step(extra):
    app, _, seen = app_with_steps()
    args = {"commands": [{"action": "eval", "args": {"n": 1}}], **extra}
    response = asyncio.run(app.execute(request(args=args)))
    assert not response.ok
    assert response.error_code == "INVALID_INPUT"
    assert seen == []


@pytest.mark.parametrize("driver", ["playwright", "extension"])
def test_isolated_batch_closes_context_on_failed_step(driver):
    app, service, _ = app_with_steps()
    service.active_driver_name = driver
    # Exercise the real child app handler with an invalid argument, before page access.
    response = asyncio.run(
        app.execute(
            request(
                args={
                    "context": {},
                    "commands": [
                        {"action": "resize", "args": {"width": 0, "height": 10}},
                    ],
                }
            )
        )
    )
    assert response.ok
    assert response.data["success"] is False
    assert service.closed
    assert response.data["context"]["closed"] is True
    assert response.data["context"]["locale"] == "en-US"
    assert response.data["state_reset"] is False
    assert response.meta["state_reset"] is False
    assert response.meta["driver"] == driver


def test_isolated_request_waits_for_other_agents_and_holds_shared_commands():
    async def scenario():
        app, _, _ = app_with_steps()
        entered = asyncio.Event()
        release = asyncio.Event()
        order = []

        async def step(req):
            order.append(req.agent_id)
            if req.agent_id == "first":
                entered.set()
                await release.wait()
            return {}

        app._handlers["eval"] = step

        async def exclusive(req):
            order.append("exclusive")
            await asyncio.sleep(0)
            return {}

        app._handlers["batch"] = exclusive
        first = asyncio.create_task(app.execute(request("eval", agent="first")))
        await entered.wait()
        context = asyncio.create_task(app.execute(request(args={"context": {}}, agent="context")))
        await asyncio.sleep(0)
        last = asyncio.create_task(app.execute(request("eval", agent="last")))
        await asyncio.sleep(0)
        assert order == ["first"]
        release.set()
        await asyncio.gather(first, context, last)
        assert order == ["first", "exclusive", "last"]

    asyncio.run(scenario())


def test_cli_batch_reads_commands_and_context_files(tmp_path):
    commands = tmp_path / "commands.json"
    commands.write_text('[{"action":"open","args":{"url":"https://example.com"}}]')
    context = tmp_path / "context.json"
    context.write_text('{"locale":"zh-CN"}')
    args = build_parser().parse_args(
        ["batch", "--file", str(commands), "--context-file", str(context), "--result-mode", "last"]
    )
    spec = next(spec for spec in get_action_specs() if spec.name == "batch")
    assert spec.build_request(args) == {
        "commands": [{"action": "open", "args": {"url": "https://example.com"}}],
        "context": {"locale": "zh-CN"},
        "stop_on_error": True,
        "result_mode": "last",
    }


def test_runtime_status_is_observable_while_a_batch_is_running():
    async def scenario():
        app, _, _ = app_with_steps()
        entered, release = asyncio.Event(), asyncio.Event()

        async def batch(req):
            entered.set()
            await release.wait()
            return {}

        async def status(req):
            return {"running": True}

        app._handlers["batch"] = batch
        app._handlers["runtime-status"] = status
        task = asyncio.create_task(app.execute(request(args={"context": {}})))
        await entered.wait()
        try:
            response = await asyncio.wait_for(app.execute(request("runtime-status")), timeout=0.2)
            assert response.data == {"running": True}
        finally:
            release.set()
            await task

    asyncio.run(scenario())


@pytest.mark.parametrize("isolated", [False, True])
@pytest.mark.parametrize("cancel_read", [False, True])
def test_batch_waits_for_async_read_and_keeps_cancellation_observable(isolated, cancel_read):
    async def scenario():
        service = Service()
        entered, release = asyncio.Event(), asyncio.Event()

        async def read(args):
            entered.set()
            await release.wait()
            return {"html": "done"}

        service.read_page_from_args = read
        app = BrowserDaemonApp(DaemonState(browser_service=service))
        steps = []

        async def step(req):
            steps.append("batch")
            return {}

        app._handlers["eval"] = step
        args = {"commands": [{"action": "eval"}]}
        if isolated:
            # The child app uses its own handlers; an invalid resize is enough
            # to observe entry after the read has released the browser.
            args.update(context={}, commands=[{"action": "resize", "args": {"width": 0}}])
        started = await app.execute(request("run-start-read", {"url": "https://example.com"}))
        await entered.wait()
        batch = asyncio.create_task(app.execute(request(args=args)))
        try:
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not batch.done(), "batch must wait for the background read"
            run_id = started.data["run_id"]
            status = await asyncio.wait_for(
                app.execute(request("run-status", {"run_id": run_id})), timeout=0.2
            )
            assert status.data["status"] == "running"
            if cancel_read:
                canceled = await asyncio.wait_for(
                    app.execute(request("run-cancel", {"run_id": run_id})), timeout=0.2
                )
                assert canceled.data["cancel_requested"]
            else:
                release.set()
            await app.state.run_registry.wait_for_idle()
            result = await asyncio.wait_for(batch, timeout=0.2)
            assert result.ok
            assert app.state.run_registry.status(run_id)["status"] == (
                "canceled" if cancel_read else "succeeded"
            )
            if isolated:
                assert service.closed
            else:
                assert steps == ["batch"]
        finally:
            release.set()
            await app.state.run_registry.wait_for_idle()
            await batch

    asyncio.run(scenario())


def test_canceled_browser_action_releases_command_lifecycle():
    async def scenario():
        app, service, _ = app_with_steps()
        entered = asyncio.Event()

        async def step(req):
            entered.set()
            await asyncio.Event().wait()

        app._handlers["eval"] = step
        task = asyncio.create_task(app.execute(request("eval")))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        service.end_command.assert_awaited_once()

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel_cleanup", [False, True])
def test_command_cleanup_is_not_repeated_when_cleanup_fails_or_is_canceled(cancel_cleanup):
    async def scenario():
        app, service, _ = app_with_steps()
        entered = asyncio.Event()

        async def end_command():
            # Repeating cleanup would decrement the shared command count again,
            # possibly allowing a backend rebind while another command is active.
            if service.end_command.await_count == 1:
                entered.set()
                if cancel_cleanup:
                    await asyncio.Event().wait()
                raise InvalidInputError("cleanup failed")
            return {}

        service.end_command.side_effect = end_command
        task = asyncio.create_task(app.execute(request("eval")))
        await entered.wait()
        if cancel_cleanup:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            result = await task
            assert not result.ok
            assert result.error_code == "INVALID_INPUT"
        service.end_command.assert_awaited_once()

    asyncio.run(scenario())


def test_background_read_queued_during_batch_can_be_canceled_without_blocking():
    async def scenario():
        service = Service()
        app = BrowserDaemonApp(DaemonState(browser_service=service))
        entered, release = asyncio.Event(), asyncio.Event()

        async def batch(req):
            entered.set()
            await release.wait()
            return {}

        app._handlers["batch"] = batch
        task = asyncio.create_task(app.execute(request()))
        await entered.wait()
        try:
            started = await asyncio.wait_for(
                app.execute(request("run-start-read", {"url": "https://example.com"})), 0.2
            )
            await asyncio.sleep(0)
            run_id = started.data["run_id"]
            assert app.state.run_registry.status(run_id)["status"] == "queued"
            await asyncio.wait_for(app.execute(request("run-cancel", {"run_id": run_id})), 0.2)
            await app.state.run_registry.wait_for_idle()
            assert app.state.run_registry.status(run_id)["status"] == "canceled"
            service.read_page_from_args.assert_not_awaited()
        finally:
            release.set()
            await task

    asyncio.run(scenario())


def test_daemon_rejects_mismatched_request_version_before_browser_work():
    app, service, seen = app_with_steps()
    req = request("eval", {"n": 1})
    req.runtime_version = "old-runtime"
    result = asyncio.run(app.execute(req))
    assert not result.ok
    assert result.error_code == "DAEMON_INCOMPATIBLE"
    assert result.meta["runtime_version"] == DAEMON_RUNTIME_VERSION
    service.begin_command.assert_not_awaited()
    assert seen == []


def test_runtime_status_advertises_the_runtime_version_without_browser_warmup():
    app, service, _ = app_with_steps()
    service.runtime_status = AsyncMock(return_value={})
    result = asyncio.run(app.execute(request("runtime-status", {"warmup": False})))
    assert result.ok
    assert result.data["runtime_version"] == DAEMON_RUNTIME_VERSION
    assert result.data["package_version"]
    service.begin_command.assert_not_awaited()


def test_canceling_a_waiting_batch_releases_new_shared_commands():
    async def scenario():
        app, _, _ = app_with_steps()
        entered, release = asyncio.Event(), asyncio.Event()
        seen = []

        async def step(req):
            seen.append(req.agent_id)
            if req.agent_id == "first":
                entered.set()
                await release.wait()
            return {}

        app._handlers["eval"] = step
        first = asyncio.create_task(app.execute(request("eval", agent="first")))
        await entered.wait()
        waiting = asyncio.create_task(app.execute(request(args={"commands": [{"action": "eval"}]})))
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        try:
            await asyncio.wait_for(app.execute(request("eval", agent="last")), 0.2)
            assert seen == ["first", "last"]
        finally:
            release.set()
            await first

    asyncio.run(scenario())


def test_canceling_continue_on_error_batch_never_starts_another_step():
    async def scenario():
        service = Service()
        app = BrowserDaemonApp(DaemonState(browser_service=service))
        entered, closing = asyncio.Event(), asyncio.Event()
        seen = []

        async def eval_step(self, req):
            seen.append(req.args["n"])
            entered.set()
            await closing.wait()
            return {}

        service.stop = AsyncMock(side_effect=closing.set)
        with patch.object(BrowserDaemonApp, "_handle_eval", eval_step):
            task = asyncio.create_task(
                app.execute(
                    request(
                        args={
                            "context": {},
                            "stop_on_error": False,
                            "commands": [{"action": "eval", "args": {"n": i}} for i in range(3)],
                        }
                    )
                )
            )
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert seen == [0]
        assert service.closed

    asyncio.run(scenario())
