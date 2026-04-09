"""CLI metadata for daemon-backed actions."""

from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


RequestBuilder = Callable[[Namespace], dict[str, Any]]
ArgumentBuilder = Callable[[ArgumentParser], None]


@dataclass(slots=True, frozen=True)
class ActionSpec:
    name: str
    help: str
    description: str
    add_arguments: ArgumentBuilder
    build_request: RequestBuilder
    start_if_needed: bool = True


def get_action_specs() -> list[ActionSpec]:
    return [
        ActionSpec("open", "Open a URL in a new tab.", "Create a new tab and navigate to URL.", _add_open_arguments, _default_request),
        ActionSpec("search", "Search the web in a new tab.", "Open a search results page in a new tab.", _add_search_arguments, _default_request),
        ActionSpec("info", "Show the current page info.", "Return the current active tab metadata.", _no_arguments, _default_request),
        ActionSpec("html", "Capture rendered DOM HTML.", "Return rendered DOM HTML for the active tab.", _no_arguments, _default_request),
        ActionSpec("snapshot", "Capture a bridgic-style snapshot.", "Return the accessibility-style snapshot tree for the active tab.", _add_snapshot_arguments, _default_request),
        ActionSpec("reload", "Reload the current page.", "Reload the current active tab.", _no_arguments, _default_request),
        ActionSpec("back", "Go back in history.", "Navigate back in the current active tab history.", _no_arguments, _default_request),
        ActionSpec("forward", "Go forward in history.", "Navigate forward in the current active tab history.", _no_arguments, _default_request),
        ActionSpec("tabs", "List visible tabs.", "List tabs visible to the current agent domain.", _no_arguments, _default_request),
        ActionSpec("new-tab", "Create a new tab.", "Open a new blank tab or navigate to URL.", _add_optional_url_arguments, _default_request),
        ActionSpec("switch-tab", "Switch the active tab.", "Switch to a visible tab by page id.", _add_page_id_arguments, _default_request),
        ActionSpec("close-tab", "Close a tab.", "Close the active tab or a visible tab by page id.", _add_optional_page_id_arguments, _default_request),
        ActionSpec("close", "Close the active tab.", "Close the current active tab in this agent domain.", _no_arguments, _default_request),
        ActionSpec("click", "Click an element ref.", "Click an element by ref.", _add_ref_arguments, _default_request),
        ActionSpec("double-click", "Double-click an element ref.", "Double-click an element by ref.", _add_ref_arguments, _default_request),
        ActionSpec("hover", "Hover an element ref.", "Hover over an element by ref.", _add_ref_arguments, _default_request),
        ActionSpec("focus", "Focus an element ref.", "Focus an element by ref.", _add_ref_arguments, _default_request),
        ActionSpec("fill", "Fill an input element by ref.", "Fill an input-like element by ref.", _add_fill_arguments, _default_request),
        ActionSpec("fill-form", "Fill multiple refs from JSON.", "Fill multiple form fields from a JSON array.", _add_fill_form_arguments, _fill_form_request),
        ActionSpec("select", "Select an option by text.", "Select an option from a dropdown ref.", _add_select_arguments, _default_request),
        ActionSpec("options", "List dropdown options.", "List all options from a dropdown ref.", _add_ref_arguments, _default_request),
        ActionSpec("check", "Check a checkbox or radio.", "Check an element by ref.", _add_ref_arguments, _default_request),
        ActionSpec("uncheck", "Uncheck a checkbox.", "Uncheck an element by ref.", _add_ref_arguments, _default_request),
        ActionSpec("scroll-to", "Scroll to an element ref.", "Scroll the active page so the ref is visible.", _add_ref_arguments, _default_request),
        ActionSpec("drag", "Drag between two refs.", "Drag from one ref to another.", _add_drag_arguments, _default_request),
        ActionSpec("upload", "Upload a file to an input ref.", "Set input files on a file input ref.", _add_upload_arguments, _default_request),
        ActionSpec("type", "Type text into the focused element.", "Type text into the currently focused element.", _add_type_arguments, _default_request),
        ActionSpec("press", "Press a keyboard key.", "Press a key or key combination.", _add_key_arguments, _default_request),
        ActionSpec("key-down", "Press and hold a key.", "Press and hold a keyboard key.", _add_key_arguments, _default_request),
        ActionSpec("key-up", "Release a key.", "Release a held keyboard key.", _add_key_arguments, _default_request),
        ActionSpec("scroll", "Scroll the page.", "Scroll the current page using mouse wheel deltas.", _add_scroll_arguments, _default_request),
        ActionSpec("mouse-click", "Click at viewport coordinates.", "Click the mouse at viewport coordinates.", _add_mouse_click_arguments, _default_request),
        ActionSpec("mouse-move", "Move the mouse.", "Move the mouse to viewport coordinates.", _add_mouse_move_arguments, _default_request),
        ActionSpec("mouse-drag", "Drag the mouse.", "Drag the mouse between viewport coordinates.", _add_mouse_drag_arguments, _default_request),
        ActionSpec("mouse-down", "Hold a mouse button.", "Press and hold a mouse button.", _add_mouse_button_arguments, _default_request),
        ActionSpec("mouse-up", "Release a mouse button.", "Release a mouse button.", _add_mouse_button_arguments, _default_request),
        ActionSpec("eval", "Evaluate JavaScript.", "Evaluate JavaScript in the page context.", _add_eval_arguments, _default_request),
        ActionSpec("eval-on", "Evaluate JavaScript on a ref.", "Evaluate JavaScript on an element ref.", _add_eval_on_arguments, _default_request),
        ActionSpec("wait", "Wait for time or text.", "Wait for time or for text to appear/disappear.", _add_wait_arguments, _default_request),
        ActionSpec("wait-network", "Wait for network idle.", "Wait until the page network is idle.", _add_wait_network_arguments, _default_request),
        ActionSpec("screenshot", "Save a screenshot.", "Save a screenshot to path.", _add_screenshot_arguments, _default_request),
        ActionSpec("pdf", "Save a PDF.", "Save the current page as a PDF.", _add_path_arguments, _default_request),
        ActionSpec("console-start", "Start console capture.", "Start capturing browser console messages.", _no_arguments, _default_request),
        ActionSpec("console", "Read console messages.", "Read captured console messages.", _add_console_arguments, _default_request),
        ActionSpec("console-stop", "Stop console capture.", "Stop capturing browser console messages.", _no_arguments, _default_request),
        ActionSpec("network-start", "Start network capture.", "Start capturing network requests.", _no_arguments, _default_request),
        ActionSpec("network", "Read network requests.", "Read captured network requests.", _add_network_arguments, _default_request),
        ActionSpec("network-stop", "Stop network capture.", "Stop capturing network requests.", _no_arguments, _default_request),
        ActionSpec("dialog-setup", "Configure automatic dialog handling.", "Automatically accept or dismiss future dialogs for the active tab.", _add_dialog_setup_arguments, _default_request),
        ActionSpec("dialog", "Configure one-time dialog handling.", "Handle the next dialog shown by the active tab.", _add_dialog_arguments, _default_request),
        ActionSpec("dialog-remove", "Remove automatic dialog handling.", "Remove the persistent dialog handler for the active tab.", _no_arguments, _default_request),
        ActionSpec("cookies", "List cookies.", "List cookies visible to the shared browser context.", _add_cookie_filter_arguments, _default_request),
        ActionSpec("cookie-set", "Set a cookie.", "Set a cookie on the shared browser context.", _add_cookie_set_arguments, _default_request),
        ActionSpec("cookies-clear", "Clear cookies.", "Clear cookies with optional filters.", _add_cookie_filter_arguments, _default_request),
        ActionSpec("storage-save", "Save storage state.", "Save cookies and localStorage to a JSON file.", _add_optional_path_arguments, _default_request),
        ActionSpec("storage-load", "Load storage state.", "Restore cookies and localStorage from a JSON file.", _add_path_arguments, _default_request),
        ActionSpec("verify-text", "Verify text is visible.", "Verify text is visible on the current page.", _add_verify_text_arguments, _default_request),
        ActionSpec("verify-visible", "Verify role/name is visible.", "Verify a role/name locator is visible.", _add_verify_visible_arguments, _default_request),
        ActionSpec("verify-url", "Verify the current URL.", "Verify the current URL against an expected value.", _add_verify_expected_arguments, _rename_expected_request),
        ActionSpec("verify-title", "Verify the current title.", "Verify the current page title.", _add_verify_expected_arguments, _rename_expected_request),
        ActionSpec("verify-state", "Verify ref state.", "Verify state for an element ref.", _add_verify_state_arguments, _default_request),
        ActionSpec("verify-value", "Verify ref value.", "Verify input value for an element ref.", _add_verify_value_arguments, _default_request),
        ActionSpec("trace-start", "Start browser tracing.", "Start Playwright tracing on the shared browser context.", _add_trace_start_arguments, _default_request),
        ActionSpec("trace-chunk", "Add a trace chunk.", "Add a named trace chunk marker to the active trace.", _add_trace_chunk_arguments, _default_request),
        ActionSpec("trace-stop", "Stop browser tracing.", "Stop tracing and save a trace archive.", _add_optional_path_arguments, _default_request),
        ActionSpec("video-start", "Start page video capture.", "Mark the active tab video capture session as started.", _add_video_start_arguments, _default_request),
        ActionSpec("video-stop", "Stop page video capture.", "Stop the active tab video capture session and choose an output path.", _add_optional_path_arguments, _default_request),
        ActionSpec("resize", "Resize the active viewport.", "Resize the active tab viewport to WIDTH x HEIGHT.", _add_resize_arguments, _default_request),
        ActionSpec("stop", "Stop the daemon.", "Stop the browser daemon and the shared browser instance.", _no_arguments, _default_request, False),
    ]


def _no_arguments(_parser: ArgumentParser) -> None:
    return


def _add_open_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("url", help="Target URL.")


def _add_optional_url_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("url", nargs="?", help="Optional target URL.")


def _add_search_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("query", help="Search query.")
    parser.add_argument(
        "--engine",
        default="duckduckgo",
        choices=["duckduckgo", "google", "bing"],
        help="Search engine to use.",
    )


def _add_snapshot_arguments(parser: ArgumentParser) -> None:
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Only keep interactive elements in the snapshot.",
    )
    parser.add_argument(
        "-F",
        "--no-full-page",
        action="store_false",
        dest="full_page",
        default=True,
        help="Limit the snapshot to the current viewport.",
    )


def _add_page_id_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("page_id", help="Visible page id, for example page_0001.")


def _add_optional_page_id_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("page_id", nargs="?", help="Optional page id. Defaults to the current active tab.")


def _add_ref_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("ref", help="Element ref from the latest snapshot.")


def _add_fill_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("ref", help="Element ref from the latest snapshot.")
    parser.add_argument("text", help="Text to fill.")
    parser.add_argument("--submit", action="store_true", help="Press Enter after filling.")


def _add_fill_form_arguments(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--fields",
        required=True,
        help='JSON array like \'[{"ref":"abcd1234","text":"hello"}]\'',
    )
    parser.add_argument("--submit", action="store_true", help="Press Enter after all fields are filled.")


def _add_select_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("ref", help="Dropdown ref.")
    parser.add_argument("text", help="Option text.")


def _add_drag_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("start_ref", help="Start ref.")
    parser.add_argument("end_ref", help="End ref.")


def _add_upload_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("ref", help="File input ref.")
    parser.add_argument("path", help="File path to upload.")


def _add_type_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("text", help="Text to type.")
    parser.add_argument("--submit", action="store_true", help="Press Enter after typing.")


def _add_key_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("key", help='Key or key combination like "Enter" or "Control+A".')


def _add_scroll_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("--dx", type=int, default=0, help="Horizontal wheel delta.")
    parser.add_argument("--dy", type=int, default=700, help="Vertical wheel delta.")


def _add_mouse_click_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("x", type=int, help="Viewport X coordinate.")
    parser.add_argument("y", type=int, help="Viewport Y coordinate.")
    parser.add_argument("--button", default="left", choices=["left", "right", "middle"], help="Mouse button.")
    parser.add_argument("--count", type=int, default=1, help="Number of clicks.")


def _add_mouse_move_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("x", type=int, help="Viewport X coordinate.")
    parser.add_argument("y", type=int, help="Viewport Y coordinate.")


def _add_mouse_drag_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("x1", type=int, help="Start X coordinate.")
    parser.add_argument("y1", type=int, help="Start Y coordinate.")
    parser.add_argument("x2", type=int, help="End X coordinate.")
    parser.add_argument("y2", type=int, help="End Y coordinate.")


def _add_mouse_button_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("--button", default="left", choices=["left", "right", "middle"], help="Mouse button.")


def _add_eval_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("code", help='Arrow function JavaScript like "() => document.title".')


def _add_eval_on_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("ref", help="Element ref from the latest snapshot.")
    parser.add_argument("code", help='Arrow function JavaScript like "(el) => el.textContent".')


def _add_wait_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("seconds", nargs="?", type=float, help="Seconds to wait when not waiting for text.")
    parser.add_argument("--text", help="Visible text to wait for.")
    parser.add_argument("--gone", action="store_true", help="Wait for the text to disappear instead of appear.")
    parser.add_argument("--exact", action="store_true", help="Use exact text matching.")


def _add_wait_network_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("--timeout", type=float, default=30.0, help="Maximum wait time in seconds.")


def _add_screenshot_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("path", help="Output path.")
    parser.add_argument("--full-page", action="store_true", help="Capture the full page.")


def _add_path_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("path", help="Path.")


def _add_optional_path_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("path", nargs="?", help="Optional path.")


def _add_dialog_setup_arguments(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--action",
        choices=["accept", "dismiss"],
        default="accept",
        help="Default action to take on future dialogs.",
    )
    parser.add_argument(
        "--text",
        help="Optional prompt text used when automatically accepting prompt dialogs.",
    )


def _add_dialog_arguments(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--dismiss",
        action="store_true",
        help="Dismiss the next dialog instead of accepting it.",
    )
    parser.add_argument(
        "--text",
        help="Optional prompt text used when accepting the next prompt dialog.",
    )


def _add_console_arguments(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--type",
        dest="message_type",
        choices=["log", "debug", "info", "error", "warning", "dir", "trace"],
        help="Optional message type filter.",
    )
    parser.add_argument("--no-clear", action="store_true", help="Keep buffered messages after reading.")


def _add_network_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("--include-static", action="store_true", help="Include images, scripts, and stylesheets.")
    parser.add_argument("--no-clear", action="store_true", help="Keep buffered requests after reading.")


def _add_cookie_filter_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("--name", help="Cookie name filter.")
    parser.add_argument("--domain", help="Cookie domain filter.")
    parser.add_argument("--path", help="Cookie path filter.")


def _add_cookie_set_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("name", help="Cookie name.")
    parser.add_argument("value", help="Cookie value.")
    parser.add_argument("--domain", help="Cookie domain. Defaults to the current page host.")
    parser.add_argument("--path", default="/", help="Cookie path.")
    parser.add_argument("--expires", type=float, help="Cookie expiry timestamp.")
    parser.add_argument("--http-only", action="store_true", help="Mark the cookie httpOnly.")
    parser.add_argument("--secure", action="store_true", help="Mark the cookie secure.")
    parser.add_argument("--same-site", choices=["Lax", "Strict", "None"], help="SameSite value.")


def _add_verify_text_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("text", help="Text to verify.")
    parser.add_argument("--exact", action="store_true", help="Use exact text matching.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Timeout in seconds.")


def _add_verify_visible_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("role", help="ARIA role.")
    parser.add_argument("name", help="Accessible name.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Timeout in seconds.")


def _add_verify_expected_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("expected", help="Expected substring or exact value.")
    parser.add_argument("--exact", action="store_true", help="Require exact equality.")


def _add_verify_state_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("ref", help="Element ref.")
    parser.add_argument(
        "state",
        choices=["visible", "hidden", "enabled", "disabled", "checked", "unchecked", "editable"],
        help="State to verify.",
    )


def _add_verify_value_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("ref", help="Element ref.")
    parser.add_argument("expected", help="Expected input value.")


def _add_trace_start_arguments(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--no-screenshots",
        action="store_true",
        help="Do not capture screenshots while tracing.",
    )
    parser.add_argument(
        "--no-snapshots",
        action="store_true",
        help="Do not capture DOM snapshots while tracing.",
    )
    parser.add_argument(
        "--sources",
        action="store_true",
        help="Include source files in the trace archive.",
    )


def _add_trace_chunk_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("title", nargs="?", help="Optional chunk title.")


def _add_video_start_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("--width", type=int, help="Requested video width.")
    parser.add_argument("--height", type=int, help="Requested video height.")


def _add_resize_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("width", type=int, help="Viewport width in pixels.")
    parser.add_argument("height", type=int, help="Viewport height in pixels.")


def _default_request(args: Namespace) -> dict[str, Any]:
    ignore = {"command", "handler", "action_name", "action_start_if_needed", "action_request_builder"}
    payload: dict[str, Any] = {}
    for key, value in vars(args).items():
        if key in ignore:
            continue
        if value is None:
            continue
        payload[key] = value
    return payload


def _fill_form_request(args: Namespace) -> dict[str, Any]:
    payload = _default_request(args)
    try:
        payload["fields"] = json.loads(str(args.fields))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for --fields: {exc}") from exc
    return payload


def _rename_expected_request(args: Namespace) -> dict[str, Any]:
    payload = _default_request(args)
    payload["expected"] = payload.pop("expected")
    return payload
