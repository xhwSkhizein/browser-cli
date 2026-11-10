"""Real-browser workflow and opt-in observation contracts, sharing one launch."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from scripts.benchmark_agent_workflows import TASKS, Replay, local_runtime

from browser_cli.constants import get_app_paths
from browser_cli.daemon.server import BrowserDaemonServer
from browser_cli.errors import NoActiveTabError

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def browser_workflows():
    loop = asyncio.new_event_loop()
    unhandled = []
    loop.set_exception_handler(lambda _loop, context: unhandled.append(context))
    manager = local_runtime()
    app, url, _executable = loop.run_until_complete(manager.__aenter__())
    try:
        yield SimpleNamespace(loop=loop, app=app, url=url)
    finally:
        loop.run_until_complete(manager.__aexit__(None, None, None))
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
    assert unhandled == [], unhandled


@pytest.fixture
def runtime(browser_workflows):
    # The shared repository fixture unlinks sockets after each test. Rebind only
    # the transport here; keep the same browser and isolated test profile.
    server = None
    path = get_app_paths().socket_path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        server = browser_workflows.loop.run_until_complete(
            asyncio.start_unix_server(
                BrowserDaemonServer(browser_workflows.app)._handle_client,
                path=str(path),
            )
        )
    try:
        yield browser_workflows
    finally:
        if server is not None:
            server.close()
            browser_workflows.loop.run_until_complete(server.wait_closed())


@pytest.mark.parametrize("task", TASKS)
@pytest.mark.parametrize("composed", [False, True])
@pytest.mark.parametrize("view", ["default", "compact", "focused"])
def test_workflow_acceptance_is_identical_for_all_views(runtime, task, composed, view):
    replay = Replay(
        runtime.app,
        runtime.url,
        compact=view != "default",
        composed=composed,
        focus_main=view == "focused",
    )
    result = runtime.loop.run_until_complete(replay.run(task))
    assert result["passed"], result
    assert result["retries"] == 0
    assert result["model_rounds"] is None and result["agent_tool_calls"] is None
    if task == "timeout":
        failed = next(response for response in replay.responses if response["data"].get("errors"))
        error = failed["data"]["errors"][0]
        assert error["error_code"] == "INTERNAL_ERROR"  # compatibility
        assert error["meta"]["failure_kind"] == "timeout"
        assert error["execution_state"] == "unknown"


def test_scoped_snapshot_preserves_actionable_refs_and_reports_truncation(runtime):
    async def scenario():
        replay = Replay(runtime.app, runtime.url)
        await replay.data("open", url=runtime.url + "/form")
        full = await replay.snapshot()
        scope = replay.ref(full, "main", "Task")
        focused = await replay.data("snapshot", compact=True, scope=scope, roles=["button"])
        assert "Reference topic" not in focused["tree"]
        assert "Preview draft" in focused["tree"]
        preview = replay.ref(focused, "button", "Preview draft")
        assert preview == replay.ref(full, "button", "Preview draft")
        await replay.data("click", ref=preview)
        limited = await replay.data("snapshot", compact=True, scope=scope, max_lines=1)
        assert limited["view"]["truncated"] is True
        # Filtering is observation control, not a second ref namespace.
        await replay.data("click", ref=preview)
        unknown = await replay.request("snapshot", scope="deadbeef", compact=True)
        assert unknown["error_code"] == "REF_NOT_FOUND" and unknown["data"] == {}
        await replay.data("close")

    runtime.loop.run_until_complete(scenario())


def test_navigation_rejects_old_ref_even_when_new_page_has_the_same_label(runtime):
    async def scenario():
        replay = Replay(runtime.app, runtime.url)
        await replay.data("open", url=runtime.url + "/resilience")
        snapshot = await replay.snapshot()
        original = replay.ref(snapshot, "button", "Original action")
        await replay.data(
            "eval", code="() => document.querySelector('#navigate').href = '/resilience?second'"
        )
        await replay.data("click", ref=replay.ref(snapshot, "link", "Account page"))
        await replay.data(
            "eval",
            code="() => { document.querySelector('#original').onclick = () => document.querySelector('#marker').textContent = 'wrong'; }",
        )
        response = await replay.request("click", ref=original)
        assert response["error_code"] == "STALE_SNAPSHOT"
        assert response["meta"]["failure_kind"] == "page_changed"
        assert response["execution_state"] == "not_started"
        marker = await replay.data(
            "eval", code="() => document.querySelector('#marker').textContent"
        )
        assert marker["result"] == "unchanged"
        await replay.data("close")

    runtime.loop.run_until_complete(scenario())


def test_interactive_scope_filters_before_truncation_and_keeps_refs_usable(runtime):
    async def scenario():
        replay = Replay(runtime.app, runtime.url)
        await replay.data("open", url=runtime.url + "/form")
        full = await replay.snapshot()
        scope = replay.ref(full, "main", "Task")
        scoped = await replay.data(
            "snapshot", compact=True, interactive=True, scope=scope, roles=["main"]
        )
        assert scoped["view"]["interactive"] is True
        assert scoped["view"]["truncated"] is False
        assert "Local draft" not in scoped["tree"] and "Reference topic" not in scoped["tree"]
        assert "Name" in scoped["tree"] and "Preview draft" in scoped["tree"]
        ref = replay.ref(scoped, "button", "Preview draft")
        assert ref == replay.ref(full, "button", "Preview draft")
        limited = await replay.data(
            "snapshot", compact=True, interactive=True, scope=scope, max_lines=1
        )
        assert limited["view"]["truncated"] is True
        assert limited["view"]["returned_lines"] == limited["view"]["returned_refs"] == 1
        assert len(limited["refs_summary"]) == 1
        assert "snapshot truncated" in limited["tree"]
        await replay.data("click", ref=ref)
        # A matching region without controls is empty, not a stale scope.
        heading = replay.ref(full, "heading", "Local draft")
        empty = await replay.data("snapshot", interactive=True, scope=heading)
        assert empty["tree"] == "(empty)" and empty["refs_summary"] == []
        assert empty["view"]["matched_lines"] == 0 and empty["view"]["truncated"] is False
        await replay.data("close")

    runtime.loop.run_until_complete(scenario())


def test_fill_form_partial_effect_is_unknown_and_blocks_later_batch_steps(runtime):
    async def scenario():
        replay = Replay(runtime.app, runtime.url)
        await replay.data("open", url=runtime.url + "/form")
        full = await replay.snapshot()
        await replay.data(
            "eval",
            code="""() => {
          window.fixtureEffects = {fills: 0, enters: 0, later: false};
          document.querySelector('input').addEventListener('input', () => {
            window.fixtureEffects.fills++;
            history.replaceState({}, '', '/form?next');
          }, {once: true});
          document.addEventListener('keydown', event => {
            if (event.key === 'Enter') window.fixtureEffects.enters++;
          });
        }""",
        )
        failed = await replay.data(
            "batch",
            result_mode="last",
            commands=[
                {
                    "action": "fill-form",
                    "args": {
                        "fields": [{"ref": replay.ref(full, "textbox", "Name"), "text": "Local"}],
                        "submit": True,
                    },
                },
                {"action": "eval", "args": {"code": "() => window.fixtureEffects.later = true"}},
            ],
        )
        assert failed["success"] is False and failed["completed_count"] == 1
        error = failed["errors"][0]
        assert error["error_code"] == "STALE_SNAPSHOT"
        assert (
            error["execution_state"] == "unknown"
            and error["meta"]["failure_kind"] == "page_changed"
        )
        effects = await replay.data(
            "eval",
            code="() => ({...window.fixtureEffects, value: document.querySelector('input').value})",
        )
        assert effects["result"] == {"fills": 1, "enters": 0, "later": False, "value": "Local"}
        await replay.data("close")

    runtime.loop.run_until_complete(scenario())


def test_completed_browser_effect_survives_cleanup_failure_without_replay(runtime):
    async def scenario():
        replay = Replay(runtime.app, runtime.url)
        await replay.data("open", url=runtime.url + "/form")
        service = runtime.app.state.browser_service
        original = service.end_command

        async def fail_after_cleanup():
            await original()
            raise NoActiveTabError("Fixture cleanup failure after browser success")

        with patch.object(service, "end_command", fail_after_cleanup):
            failed = await replay.data(
                "batch",
                commands=[
                    {"action": "eval", "args": {"code": "() => window.fixtureEffects = 1"}},
                    {"action": "eval", "args": {"code": "() => window.fixtureEffects++"}},
                ],
            )
        assert failed["success"] is False and failed["completed_count"] == 1
        assert failed["errors"][0]["execution_state"] == "completed"
        result = await replay.data("eval", code="() => window.fixtureEffects")
        assert result["result"] == 1
        await replay.data("close")

    runtime.loop.run_until_complete(scenario())
