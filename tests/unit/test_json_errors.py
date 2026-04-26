from __future__ import annotations

import json

from browser_cli import error_codes
from browser_cli.errors import WorkspaceBindingLostError
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


def test_new_recovery_error_codes_are_stable() -> None:
    assert error_codes.WORKSPACE_BINDING_LOST == "WORKSPACE_BINDING_LOST"
    assert error_codes.EXTENSION_PORT_IN_USE == "EXTENSION_PORT_IN_USE"
    assert error_codes.CHROME_EXECUTABLE_NOT_FOUND == "CHROME_EXECUTABLE_NOT_FOUND"
    assert error_codes.HEADLESS_RUNTIME_UNAVAILABLE == "HEADLESS_RUNTIME_UNAVAILABLE"
