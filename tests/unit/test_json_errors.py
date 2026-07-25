from __future__ import annotations

import json

from browser_cli import error_codes
from browser_cli.errors import EmptyContentError, WorkspaceBindingLostError
from browser_cli.outputs.json import render_json_error


def test_render_json_error_uses_next_action() -> None:
    payload = json.loads(
        render_json_error(
            WorkspaceBindingLostError("Workspace binding was lost."),
            next_action="browser-cli workspace rebuild --json",
        )
    )
    assert payload == {
        "ok": False,
        "error_code": "WORKSPACE_BINDING_LOST",
        "message": "Workspace binding was lost.",
        "next_action": "browser-cli workspace rebuild --json",
    }


def test_render_json_error_includes_details() -> None:
    payload = json.loads(
        render_json_error(
            EmptyContentError(
                details={
                    "url": "https://example.com",
                    "final_url": "https://example.com/",
                    "title": "",
                    "body_len": 0,
                    "output_mode": "html",
                    "driver": "extension",
                }
            ),
            action="read",
            next_action="retry with --scroll-bottom or a longer --settle-ms",
        )
    )
    assert payload["ok"] is False
    assert payload["error_code"] == "EMPTY_CONTENT"
    assert payload["details"]["body_len"] == 0
    assert payload["details"]["driver"] == "extension"
    assert payload["meta"] == {"action": "read"}
    assert "settle-ms" in payload["next_action"]


def test_render_json_error_can_include_action_meta() -> None:
    payload = json.loads(
        render_json_error(
            WorkspaceBindingLostError("Workspace binding was lost."),
            action="workspace-rebuild",
            next_action="browser-cli workspace rebuild --json",
        )
    )
    assert payload == {
        "ok": False,
        "error_code": "WORKSPACE_BINDING_LOST",
        "message": "Workspace binding was lost.",
        "meta": {"action": "workspace-rebuild"},
        "next_action": "browser-cli workspace rebuild --json",
    }


def test_new_recovery_error_codes_are_stable() -> None:
    assert error_codes.WORKSPACE_BINDING_LOST == "WORKSPACE_BINDING_LOST"
    assert error_codes.EXTENSION_PORT_IN_USE == "EXTENSION_PORT_IN_USE"
    assert error_codes.CHROME_EXECUTABLE_NOT_FOUND == "CHROME_EXECUTABLE_NOT_FOUND"
    assert error_codes.HEADLESS_RUNTIME_UNAVAILABLE == "HEADLESS_RUNTIME_UNAVAILABLE"
