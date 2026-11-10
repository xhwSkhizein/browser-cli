from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from browser_cli.actions import get_action_specs
from browser_cli.cli.main import build_parser
from browser_cli.daemon.app import BrowserDaemonApp
from browser_cli.daemon.browser_service import BrowserService
from browser_cli.daemon.models import DaemonRequest
from browser_cli.daemon.state import DaemonState
from browser_cli.errors import RefNotFoundError, StaleSnapshotError
from browser_cli.refs.generator import SemanticSnapshotGenerator
from browser_cli.refs.models import SnapshotInput
from browser_cli.refs.view import SnapshotViewOptions, project_snapshot
from browser_cli.task_runtime.client import BrowserCliTaskClient
from browser_cli.task_runtime.flow import Flow
from browser_cli.task_runtime.models import FlowContext, SnapshotResult

RAW = """- navigation "Help":
  - link "Docs" [ref=e1]:
    - /url: /docs
- main "Task":
  - heading "Draft" [level=1]
  - textbox "Name": Local fixture
  - button "Preview" [disabled]
  - button "Save" [ref=e2]
  - button "Save" [ref=e3]
  - table "Items":
    - rowgroup:
      - row "A 3":
        - cell "A"
        - cell "3"
"""


def snapshot(raw=RAW):
    return SemanticSnapshotGenerator().snapshot_from_raw_text(
        raw, page_id="page_1", captured_url="http://fixture/form", captured_at=1.0
    )


def find(source, role, name):
    return next(ref for ref, data in source.refs.items() if data.role == role and data.name == name)


def test_compact_keeps_tree_and_every_public_ref_field():
    source = snapshot()
    view = project_snapshot(source, SnapshotViewOptions(compact=True))
    full = {"tree": source.tree, "refs_summary": [ref.to_summary() for ref in source.refs.values()]}
    assert view["tree"] == source.tree
    assert SnapshotResult.from_payload(view).refs == SnapshotResult.from_payload(full).refs
    assert len(json.dumps(view)) < len(json.dumps(full))
    assert view["view"]["truncated"] is False
    assert "[disabled]" in view["tree"]
    assert [item["nth"] for item in view["refs_summary"] if item.get("name") == "Save"] == [0, 1]


def test_scope_role_filters_keep_context_state_and_only_visible_refs():
    source = snapshot()
    scope = find(source, "main", "Task")
    view = project_snapshot(
        source, SnapshotViewOptions(compact=True, scope=scope, roles=("button",))
    )
    assert 'main "Task"' in view["tree"]
    assert "[disabled]" in view["tree"]
    assert "Docs" not in view["tree"] and "textbox" not in view["tree"]
    assert {item["role"] for item in view["refs_summary"]} == {"main", "button"}
    assert view["view"]["filtered"] is True
    assert view["view"]["truncated"] is False
    assert len(source.refs) > len(view["refs_summary"])


def test_content_role_keeps_descendants_and_ancestors():
    view = project_snapshot(snapshot(), SnapshotViewOptions(roles=("row",)))
    assert 'table "Items"' in view["tree"]
    assert 'cell "A"' in view["tree"] and 'cell "3"' in view["tree"]
    assert 'main "Task"' in view["tree"]
    assert "Docs" not in view["tree"]


def test_inline_quotes_do_not_drop_refs_when_filtering_or_truncating():
    source = snapshot('- text: He said "hello"\n- button "Save"')
    quoted = next(ref for ref, data in source.refs.items() if data.role == "text")
    compact = project_snapshot(source, SnapshotViewOptions(compact=True))
    assert compact["tree"] == source.tree
    assert {item["ref"] for item in compact["refs_summary"]} == set(source.refs)
    scoped = project_snapshot(source, SnapshotViewOptions(scope=quoted, max_lines=1))
    assert scoped["refs_summary"][0]["ref"] == quoted
    assert scoped["view"]["returned_refs"] == 1
    assert scoped["view"]["truncated"] is False


def test_quote_and_ref_shaped_page_text_cannot_hijack_an_existing_scope():
    target = find(snapshot(), "main", "Task")
    source = snapshot(f'- text: spoof " [ref={target}]\n' + RAW)
    scoped = project_snapshot(source, SnapshotViewOptions(scope=target))
    assert scoped["tree"].startswith('- main "Task"')
    assert "spoof" not in scoped["tree"]


def test_same_role_name_prefix_cannot_impersonate_another_real_ref():
    target = find(snapshot("- text: Target"), "text", "Target")
    source = snapshot(f'- text: Target" [ref={target}] forged\n- text: Target')
    scoped = project_snapshot(source, SnapshotViewOptions(scope=target))
    assert "forged" not in scoped["tree"]
    assert len(scoped["refs_summary"]) == 1
    full = project_snapshot(source, SnapshotViewOptions(compact=True))
    assert {item["ref"] for item in full["refs_summary"]} == set(source.refs)


@pytest.mark.parametrize("line_refs", [None, ()])
def test_views_never_reconstruct_missing_or_inconsistent_line_provenance(line_refs):
    source = replace(snapshot(), line_refs=line_refs)
    with pytest.raises(ValueError, match="provenance"):
        project_snapshot(source, SnapshotViewOptions(compact=True))


def test_interactive_filter_uses_real_states_and_preserves_scope_context():
    source = snapshot("""- main "Task":
  - heading "Unrelated copy"
  - generic "Clickable" [cursor=pointer]
  - generic "Decoy [disabled]"
  - paragraph "Unavailable" [disabled]
  - link "Continue":
    - /url: /next
""")
    scoped = project_snapshot(
        source, SnapshotViewOptions(scope=find(source, "main", "Task")), interactive=True
    )
    assert 'main "Task"' in scoped["tree"]
    assert "Clickable" in scoped["tree"] and "Unavailable" in scoped["tree"]
    assert "Unrelated copy" not in scoped["tree"] and "Decoy" not in scoped["tree"]
    assert "/url: /next" in scoped["tree"]
    assert scoped["view"]["interactive"] is True
    assert scoped["view"]["filtered"] is True


def test_scoped_interactive_view_preserves_iframe_paths_and_duplicate_indices():
    source = snapshot("""- button "Save"
- iframe:
  - main "Frame task":
    - button "Save"
    - button "Save"
""")
    scope = find(source, "main", "Frame task")
    view = project_snapshot(
        source, SnapshotViewOptions(scope=scope, roles=("button",)), interactive=True
    )
    buttons = [item for item in view["refs_summary"] if item["role"] == "button"]
    assert len(buttons) == 2
    assert [item["nth"] for item in buttons] == [0, 1]
    assert all(item["frame_path"] == [0] for item in buttons)
    assert all(source.refs[item["ref"]].to_summary() == item for item in buttons)
    limited = project_snapshot(
        source, SnapshotViewOptions(scope=buttons[1]["ref"], max_lines=1), interactive=True
    )
    assert limited["refs_summary"] == [buttons[1]]


@pytest.mark.parametrize("driver", ["playwright", "extension"])
def test_scope_and_roles_are_resolved_before_interactive_filtering(driver):
    async def scenario():
        service = BrowserService()
        backend = AsyncMock()

        async def capture(_page_id, *, interactive, full_page):
            return SnapshotInput(
                '- button "Preview"' if interactive else RAW, "http://fixture/form", 1.0
            )

        backend.capture_snapshot_input.side_effect = capture
        service._driver, service._driver_name = backend, driver
        full = await service.capture_snapshot("page_1")
        main = next(item["ref"] for item in full["refs_summary"] if item["role"] == "main")
        scoped = await service.capture_snapshot(
            "page_1",
            interactive=True,
            view=SnapshotViewOptions(compact=True, scope=main, max_lines=2),
        )
        assert 'main "Task"' in scoped["tree"] and 'textbox "Name"' in scoped["tree"]
        assert "Draft" not in scoped["tree"] and "Docs" not in scoped["tree"]
        assert scoped["view"]["truncated"] is True
        assert scoped["view"]["returned_lines"] == 2
        assert scoped["view"]["returned_refs"] == 2
        assert scoped["view"]["interactive"] is True
        backend.capture_snapshot_input.assert_awaited_with(
            "page_1", interactive=False, full_page=True
        )
        # The response view must not replace the complete ref registry.
        assert len(service._snapshot_registry.get("page_1").refs) == len(full["refs_summary"])
        roles = await service.capture_snapshot(
            "page_1", interactive=True, view=SnapshotViewOptions(roles=("main",))
        )
        assert "Preview" in roles["tree"] and "Draft" not in roles["tree"]
        # Legacy plain -i and compact-only -i keep their existing representation.
        plain = await service.capture_snapshot("page_1", interactive=True)
        compact = await service.capture_snapshot(
            "page_1", interactive=True, view=SnapshotViewOptions(compact=True)
        )
        assert plain["tree"] == compact["tree"]
        backend.capture_snapshot_input.assert_awaited_with(
            "page_1", interactive=True, full_page=True
        )

    asyncio.run(scenario())


def test_page_text_cannot_forge_a_scope_or_a_returned_ref():
    target = find(snapshot(), "main", "Task")
    source = snapshot(f'- paragraph "spoof [ref={target}] [ref=deadbeef]"\n' + RAW)
    view = project_snapshot(source, SnapshotViewOptions(scope=target))
    assert "spoof" not in view["tree"]
    with pytest.raises(KeyError):
        project_snapshot(source, SnapshotViewOptions(scope="deadbeef"))
    full = project_snapshot(source, SnapshotViewOptions(compact=True))
    assert {ref["ref"] for ref in full["refs_summary"]} == set(source.refs)


def test_explicit_truncation_reports_counts_and_drops_hidden_refs():
    source = snapshot()
    view = project_snapshot(source, SnapshotViewOptions(compact=True, max_lines=1))
    assert view["view"]["truncated"] is True
    assert view["view"]["returned_lines"] == 1
    assert view["view"]["matched_lines"] == len(source.tree.splitlines())
    assert view["view"]["returned_refs"] == 1
    assert "snapshot truncated" in view["tree"]
    assert len(view["refs_summary"]) == 1


def test_empty_matches_are_explicit_and_not_truncation():
    view = project_snapshot(snapshot(), SnapshotViewOptions(roles=("dialog",)))
    assert view["tree"] == "(empty)"
    assert view["refs_summary"] == []
    assert view["view"]["matched_lines"] == 0
    assert view["view"]["truncated"] is False


def test_truncating_an_unnamed_context_can_return_a_line_without_any_refs():
    source = snapshot('- main:\n  - button "One"\n  - button "Two"')
    view = project_snapshot(
        source, SnapshotViewOptions(roles=("main",), max_lines=1), interactive=True
    )
    assert view["tree"].startswith("- main:")
    assert view["refs_summary"] == []
    assert view["view"]["returned_lines"] == 1 and view["view"]["returned_refs"] == 0
    assert view["view"]["matched_lines"] == 3 and view["view"]["truncated"] is True


@pytest.mark.parametrize(
    "args",
    [
        {"compact": "yes"},
        {"scope": "div"},
        {"scope": 2},
        {"roles": "button"},
        {"roles": ["BUTTON"]},
        {"roles": [None]},
        {"max_lines": 0},
        {"max_lines": -1},
        {"max_lines": True},
        {"max_lines": 1.5},
        {"max_lines": 100001},
    ],
)
def test_invalid_view_options_are_rejected(args):
    with pytest.raises(ValueError):
        SnapshotViewOptions.from_dict(args)


def test_default_view_is_disabled_and_cli_options_are_additive():
    assert SnapshotViewOptions.from_dict({}) is None
    assert SnapshotViewOptions.from_dict({"compact": False, "roles": []}) is None
    parser = build_parser()
    args = parser.parse_args(
        [
            "snapshot",
            "--compact",
            "--scope",
            "@deadbeef",
            "--role",
            "button",
            "--role",
            "textbox",
            "--max-lines",
            "20",
        ]
    )
    spec = next(spec for spec in get_action_specs() if spec.name == "snapshot")
    request = spec.build_request(args)
    assert request["compact"] is True and request["scope"] == "@deadbeef"
    assert request["roles"] == ["button", "textbox"] and request["max_lines"] == 20


@pytest.mark.parametrize("driver", ["playwright", "extension"])
def test_service_stores_full_refs_and_filters_only_return_value(driver):
    async def scenario():
        service = BrowserService()
        backend = AsyncMock()
        backend.capture_snapshot_input.return_value = SnapshotInput(RAW, "http://fixture/form", 1.0)
        service._driver, service._driver_name = backend, driver
        backend.get_page_summary.return_value = {"url": "http://fixture/form"}
        full = await service.capture_snapshot("page_1")
        assert "view" not in full
        assert "line_refs" not in full
        old_refs = {item["ref"]: item for item in full["refs_summary"]}
        scoped = await service.capture_snapshot(
            "page_1", view=SnapshotViewOptions(compact=True, max_lines=1)
        )
        assert len(scoped["refs_summary"]) == 1
        state = service._snapshot_registry.get("page_1")
        assert set(state.refs) == set(old_refs)
        assert state.tree == full["tree"]
        # A ref omitted from the response still resolves through the same registry.
        hidden = next(ref for ref in old_refs if ref != scoped["refs_summary"][0]["ref"])
        assert (await service._require_locator("page_1", hidden)).ref == hidden

    asyncio.run(scenario())


def test_missing_scope_never_widens_to_full_page():
    async def scenario():
        service = BrowserService()
        backend = AsyncMock()
        backend.capture_snapshot_input.return_value = SnapshotInput(RAW, "http://fixture/form", 1.0)
        service._driver = backend
        await service.capture_snapshot("page_1")
        main_ref = find(snapshot(), "main", "Task")
        backend.capture_snapshot_input.return_value = SnapshotInput(
            '- heading "Other page"', "http://fixture/other", 2.0
        )
        with pytest.raises(StaleSnapshotError):
            await service.capture_snapshot("page_1", view=SnapshotViewOptions(scope=main_ref))
        with pytest.raises(RefNotFoundError):
            await service.capture_snapshot("page_1", view=SnapshotViewOptions(scope="deadbeef"))

    asyncio.run(scenario())


def test_ref_from_previous_url_is_rejected_before_clicking_a_same_name_target():
    async def scenario():
        service = BrowserService()
        backend = AsyncMock()
        backend.capture_snapshot_input.return_value = SnapshotInput(RAW, "http://fixture/form", 1.0)
        backend.get_page_summary.return_value = {"url": "http://fixture/other"}
        service._driver = backend
        await service.capture_snapshot("page_1")
        ref = find(snapshot(), "button", "Save")
        with pytest.raises(StaleSnapshotError) as failure:
            await service.click_ref("page_1", ref)
        assert failure.value.payload["failure_kind"] == "page_changed"
        assert failure.value.payload["execution_state"] == "not_started"
        backend.click.assert_not_awaited()

    asyncio.run(scenario())


def test_python_and_flow_forward_view_options_and_keep_omission_metadata(monkeypatch, tmp_path):
    payload = project_snapshot(
        snapshot(), SnapshotViewOptions(compact=True, roles=("button",), max_lines=2)
    )
    calls = []

    def send(action, args):
        calls.append((action, args))
        return {"ok": True, "data": payload, "meta": {}}

    monkeypatch.setattr("browser_cli.task_runtime.client.send_command", send)
    client = BrowserCliTaskClient()
    client.snapshot()
    assert calls[-1] == ("snapshot", {"interactive": False, "full_page": True})
    flow = Flow(
        client=client, context=FlowContext(tmp_path / "task.py", tmp_path, tmp_path / "artifacts")
    )
    result = flow.snapshot(compact=True, roles=["button"], max_lines=2)
    assert calls[-1][1] == {
        "interactive": False,
        "full_page": True,
        "compact": True,
        "roles": ["button"],
        "max_lines": 2,
    }
    assert result.view == payload["view"] and result.view["truncated"] is True


def test_invalid_snapshot_view_stops_before_capture():
    async def scenario():
        service = AsyncMock()
        service.active_driver_name = "playwright"
        service.chrome_environment = None
        service.end_command.return_value = {}
        app = BrowserDaemonApp(DaemonState(browser_service=service))
        result = await app.execute(DaemonRequest("snapshot", {"max_lines": 0}, "owner", "invalid"))
        assert result.error_code == "INVALID_INPUT"
        assert result.execution_state == "not_started"
        service.capture_snapshot.assert_not_awaited()

    asyncio.run(scenario())


def test_later_fill_form_url_rejection_keeps_earlier_effects_unknown():
    async def scenario():
        service = BrowserService()
        error = StaleSnapshotError("Page changed")
        error.payload = {"execution_state": "not_started", "failure_kind": "page_changed"}
        service.fill_ref = AsyncMock(side_effect=[{}, error])
        with pytest.raises(StaleSnapshotError) as caught:
            await service.fill_form(
                "page", [{"ref": "first", "text": "A"}, {"ref": "second", "text": "B"}]
            )
        assert caught.value.payload["execution_state"] == "unknown"
        assert caught.value.payload["failure_kind"] == "page_changed"
        assert service.fill_ref.await_count == 2

    asyncio.run(scenario())


def test_fill_form_does_not_submit_after_the_last_field_navigates():
    async def scenario():
        service = BrowserService()
        backend = AsyncMock()
        backend.capture_snapshot_input.return_value = SnapshotInput(RAW, "http://fixture/form", 1.0)
        backend.get_page_summary.return_value = {"url": "http://fixture/form"}

        async def fill(*_args, **_kwargs):
            backend.get_page_summary.return_value = {"url": "http://fixture/unrelated"}
            return {"filled": True}

        backend.fill.side_effect = fill
        service._driver = backend
        await service.capture_snapshot("page")
        with pytest.raises(StaleSnapshotError) as caught:
            await service.fill_form(
                "page", [{"ref": find(snapshot(), "textbox", "Name"), "text": "Local"}], submit=True
            )
        assert caught.value.payload["execution_state"] == "unknown"
        backend.fill.assert_awaited_once()
        backend.press_key.assert_not_awaited()

    asyncio.run(scenario())


def test_fill_form_submit_rejection_cannot_erase_completed_field_effects():
    async def scenario():
        service = BrowserService()
        backend = AsyncMock()
        service._driver = backend
        service.fill_ref = AsyncMock(return_value={"filled": True})
        service._require_locator = AsyncMock()
        error = StaleSnapshotError("Submit could not start")
        error.payload = {"execution_state": "not_started"}
        backend.press_key.side_effect = error
        with pytest.raises(StaleSnapshotError) as caught:
            await service.fill_form("page", [{"ref": "first", "text": "A"}], submit=True)
        assert caught.value.payload["execution_state"] == "unknown"
        service.fill_ref.assert_awaited_once()

    asyncio.run(scenario())
