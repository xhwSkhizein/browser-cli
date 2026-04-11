from __future__ import annotations

from browser_cli.actions import get_action_specs

BRIDGIC_COMMANDS = {
    "open",
    "search",
    "info",
    "reload",
    "back",
    "forward",
    "snapshot",
    "click",
    "fill",
    "fill-form",
    "scroll-to",
    "select",
    "options",
    "check",
    "uncheck",
    "focus",
    "hover",
    "double-click",
    "upload",
    "drag",
    "tabs",
    "new-tab",
    "switch-tab",
    "close-tab",
    "eval",
    "eval-on",
    "press",
    "type",
    "key-down",
    "key-up",
    "scroll",
    "mouse-click",
    "mouse-move",
    "mouse-drag",
    "mouse-down",
    "mouse-up",
    "wait",
    "screenshot",
    "pdf",
    "network-wait",
    "network-start",
    "network",
    "network-stop",
    "wait-network",
    "dialog-setup",
    "dialog",
    "dialog-remove",
    "cookies",
    "cookie-set",
    "cookies-clear",
    "storage-save",
    "storage-load",
    "verify-text",
    "verify-visible",
    "verify-url",
    "verify-title",
    "verify-state",
    "verify-value",
    "console-start",
    "console",
    "console-stop",
    "trace-start",
    "trace-chunk",
    "trace-stop",
    "video-start",
    "video-stop",
    "close",
    "resize",
}


def test_action_catalog_covers_bridgic_surface() -> None:
    names = {spec.name for spec in get_action_specs()}
    assert names >= BRIDGIC_COMMANDS


def test_browser_cli_only_adds_documented_extensions() -> None:
    names = {spec.name for spec in get_action_specs()}
    assert names - BRIDGIC_COMMANDS == {"html", "stop"}
