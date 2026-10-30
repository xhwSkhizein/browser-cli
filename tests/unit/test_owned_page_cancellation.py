"""Owned-page cancellation at the daemon/registry and socket boundaries."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from browser_cli.daemon.app import BrowserDaemonApp
from browser_cli.daemon.browser_service import BrowserService
from browser_cli.daemon.models import DaemonRequest
from browser_cli.daemon.server import BrowserDaemonServer
from browser_cli.daemon.state import DaemonState
from browser_cli.errors import OperationFailedError
from browser_cli.tabs.registry import TabRegistry


class Service:
    active_driver_name = "extension"
    chrome_environment = None

    def __init__(self):
        self.started = {page: asyncio.Event() for page in ("owned", "peer")}
        self.stopped = {page: asyncio.Event() for page in self.started}
        self.closed = []
        self.close_error = None
        self.close_confirmed = True
        self.summary_calls = []

    async def read_page_from_args(self, args):
        raise NotImplementedError

    async def begin_command(self, action):
        pass

    async def end_command(self, **kwargs):
        return {"driver": "extension"}

    async def evaluate(self, page_id, code):
        self.started[page_id].set()
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped[page_id].set()

    async def close_tab(self, page_id):
        if self.close_error:
            raise self.close_error
        self.closed.append(page_id)
        return {"page_id": page_id, "closed": self.close_confirmed}

    async def get_page_summary(self, page_id):
        self.summary_calls.append(page_id)
        return {"page_id": page_id, "url": "http://fixture/", "title": "fixture"}


def request(action, page=None, agent="owner", identifier="cleanup"):
    args = {"page_id": page} if page else {"code": "async () => fetch('/slow')"}
    return DaemonRequest(action, args, agent, identifier)


async def fixture(service=None):
    tabs = TabRegistry()
    await tabs.add_tab(page_id="owned", owner_agent_id="owner")
    await tabs.add_tab(page_id="peer", owner_agent_id="other")
    service = service or Service()
    app = BrowserDaemonApp(DaemonState(tabs=tabs, browser_service=service))
    return app, tabs, service


async def drain(*tasks):
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def test_owned_close_stops_its_operation_after_browser_ack_and_preserves_peer():
    async def scenario():
        app, tabs, service = await fixture()
        running = asyncio.create_task(app.execute(request("eval", identifier="running")))
        peer = asyncio.create_task(app.execute(request("eval", agent="other", identifier="peer")))
        try:
            await asyncio.wait_for(service.started["owned"].wait(), 1)
            await asyncio.wait_for(service.started["peer"].wait(), 1)
            closed = await asyncio.wait_for(app.execute(request("close-tab", "owned")), 1)
            assert closed.ok, closed.to_dict()
            assert closed.data["interruption"] == {
                "request_id": "running",
                "page_closed": True,
                "command_drained": True,
                "execution_state": "unknown",
            }
            assert service.closed == ["owned"]
            assert service.stopped["owned"].is_set()
            assert not service.stopped["peer"].is_set()
            assert not peer.done()
            assert await tabs.list_tabs("owner") == []
            assert (await tabs.get_active_tab("other")).page_id == "peer"
            assert (await tabs.get_active_tab("other")).busy.request_id == "peer"
        finally:
            await drain(running, peer)
        assert tabs._claim_tasks == {}

    asyncio.run(scenario())


def test_foreign_close_cannot_interrupt_or_disclose_the_owners_operation():
    async def scenario():
        app, tabs, service = await fixture()
        running = asyncio.create_task(app.execute(request("eval", identifier="private-request")))
        try:
            await service.started["owned"].wait()
            denied = await app.execute(request("close-tab", "owned", agent="other"))
            assert denied.error_code == "TAB_NOT_FOUND"
            assert "private-request" not in json.dumps(denied.to_dict())
            assert service.closed == []
            assert not running.done()
            assert (await tabs.get_active_tab("owner")).busy.request_id == "private-request"
        finally:
            await drain(running)

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["error", "unconfirmed"])
def test_unconfirmed_close_keeps_running_work_claimed_and_reports_unknown(mode):
    async def scenario():
        app, tabs, service = await fixture()
        if mode == "error":
            service.close_error = OperationFailedError("Remote close could not be confirmed")
        else:
            service.close_confirmed = False
        running = asyncio.create_task(app.execute(request("eval", identifier="running")))
        try:
            await service.started["owned"].wait()
            failed = await app.execute(request("close-tab", "owned"))
            assert failed.ok is False
            assert failed.to_dict()["execution_state"] == "unknown"
            assert not running.done()
            assert not service.stopped["owned"].is_set()
            record = await tabs.get_active_tab("owner")
            assert record.closing is None
            assert record.busy.request_id == "running"
            busy = await app.execute(request("eval", identifier="retry"))
            assert busy.error_code == "AGENT_ACTIVE_TAB_BUSY"
            assert busy.to_dict()["execution_state"] == "not_started"
        finally:
            await drain(running)

    asyncio.run(scenario())


def test_late_result_cannot_restore_closed_tab_or_publish_a_success():
    async def scenario():
        late = asyncio.Event()
        app, tabs, service = await fixture()
        await tabs.add_tab(page_id="kept", owner_agent_id="owner")
        await tabs.set_active_tab("owner", "owned")

        async def suppress_cancel(page_id, code):
            service.started[page_id].set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await late.wait()
                return {"result": "late"}

        service.evaluate = suppress_cancel
        running = asyncio.create_task(app.execute(request("eval", identifier="running")))
        try:
            await service.started["owned"].wait()
            closed = await app.execute(request("close-tab", "owned"))
            assert closed.ok
            assert closed.data["interruption"]["command_drained"] is False
            late.set()
            response = await asyncio.wait_for(running, 1)
            assert response.error_code == "OPERATION_CANCELLED"
            assert response.to_dict()["execution_state"] == "unknown"
            assert (await tabs.get_active_tab("owner")).page_id == "kept"
            assert service.summary_calls == []
            assert tabs._claim_tasks == {}
        finally:
            late.set()
            await drain(running)

    asyncio.run(scenario())


def test_owned_close_can_interrupt_a_batch_without_running_its_next_step():
    async def scenario():
        app, tabs, service = await fixture()
        after = AsyncMock(return_value={})
        app._handlers["info"] = after
        running = asyncio.create_task(
            app.execute(
                DaemonRequest(
                    "batch",
                    {
                        "commands": [
                            {"action": "eval", "args": {"code": "async () => fetch('/slow')"}},
                            {"action": "info"},
                        ],
                        "stop_on_error": False,
                    },
                    "owner",
                    "batch-request",
                )
            )
        )
        try:
            await service.started["owned"].wait()
            closed = await asyncio.wait_for(app.execute(request("close-tab", "owned")), 1)
            assert closed.ok
            assert running.cancelled()
            after.assert_not_awaited()
            assert await tabs.list_tabs("owner") == []
            assert app.state.execution._active == 0
        finally:
            await drain(running)

    asyncio.run(scenario())


def test_server_returns_single_json_for_interrupted_request_and_closes_socket():
    async def scenario():
        app, tabs, service = await fixture()
        reader = asyncio.StreamReader()
        reader.feed_data(
            (
                json.dumps(
                    {
                        "action": "eval",
                        "args": {"code": "async () => fetch('/slow')"},
                        "agent_id": "owner",
                        "request_id": "running",
                    }
                )
                + "\n"
            ).encode()
        )
        reader.feed_eof()
        writer = MagicMock()
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()
        running = asyncio.create_task(BrowserDaemonServer(app)._handle_client(reader, writer))
        try:
            await service.started["owned"].wait()
            closed = await app.execute(request("close-tab", "owned"))
            assert closed.ok
            await asyncio.wait_for(running, 1)
            writer.write.assert_called_once()
            result = json.loads(writer.write.call_args.args[0])
            assert result["ok"] is False
            assert result["error_code"] == "OPERATION_CANCELLED"
            assert result["execution_state"] == "unknown"
            assert result["meta"] == {
                "action": "eval",
                "agent_id": "owner",
                "request_id": "running",
            }
            writer.close.assert_called_once()
            assert tabs._claim_tasks == {}
        finally:
            await drain(running)

    asyncio.run(scenario())


def test_owned_close_waits_for_global_lifecycle_change():
    async def scenario():
        app, _, service = await fixture()
        entered, release = asyncio.Event(), asyncio.Event()

        async def stopping(req):
            entered.set()
            await release.wait()
            return {"stopped": True}

        app._handlers["stop"] = stopping
        stopping_task = asyncio.create_task(app.execute(request("stop", identifier="stop")))
        await entered.wait()
        closing_task = asyncio.create_task(app.execute(request("close-tab", "owned")))
        try:
            await asyncio.sleep(0)
            assert service.closed == []
            assert not closing_task.done()
            release.set()
            await stopping_task
            assert (await closing_task).ok
            assert service.closed == ["owned"]
        finally:
            release.set()
            await drain(stopping_task, closing_task)

    asyncio.run(scenario())


def test_cleanup_never_starts_rebuilds_or_rebinds_browser(monkeypatch, tmp_path):
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / "runtime"))

    async def scenario():
        service = BrowserService(TabRegistry())
        service._driver = object()
        service._driver_name = "extension"
        service.ensure_started = AsyncMock()
        service._maybe_preflight_workspace_binding = AsyncMock()
        service._maybe_apply_pending_rebind = AsyncMock()
        await service.begin_command("close-tab")
        await service.end_command(allow_rebind=False)
        service.ensure_started.assert_not_awaited()
        service._maybe_preflight_workspace_binding.assert_not_awaited()
        service._maybe_apply_pending_rebind.assert_not_awaited()
        assert service._command_depth == 0

    asyncio.run(scenario())
