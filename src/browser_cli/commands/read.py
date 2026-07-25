"""Read command handler."""

from __future__ import annotations

import sys
from argparse import Namespace

from browser_cli.daemon.client import send_command
from browser_cli.errors import InvalidInputError
from browser_cli.outputs.json import render_json_payload
from browser_cli.outputs.render import render_output
from browser_cli.task_runtime import BrowserCliTaskClient


def normalize_url(url: str) -> str:
    if "://" in url:
        return url
    return f"https://{url}"


def run_read_command(args: Namespace) -> str:
    if bool(getattr(args, "async_run", False)):
        return _run_read_async(args)
    client = BrowserCliTaskClient()
    output_mode = "snapshot" if args.snapshot else "html"
    settle_ms = _settle_ms_from_args(args)
    result = client.read(
        normalize_url(args.url),
        output_mode=output_mode,
        scroll_bottom=bool(args.scroll_bottom),
        settle_ms=settle_ms,
    )
    if getattr(args, "json", False):
        return render_json_payload(
            {
                "ok": True,
                "data": {
                    "body": result.body,
                    "output_mode": output_mode,
                    "used_fallback_profile": result.used_fallback_profile,
                    "fallback_profile_dir": result.fallback_profile_dir,
                    "fallback_reason": result.fallback_reason,
                },
                "meta": {"action": "read"},
            }
        )
    if result.used_fallback_profile and result.fallback_profile_dir:
        message = (
            "Info: primary Chrome profile unavailable; using fallback profile at "
            f"{result.fallback_profile_dir}"
        )
        if result.fallback_reason:
            message += f". Reason: {result.fallback_reason}"
        sys.stderr.write(message + "\n")
    return render_output(result.body)


def _run_read_async(args: Namespace) -> str:
    if not getattr(args, "json", False):
        raise InvalidInputError("read --async requires --json")
    output_mode = "snapshot" if args.snapshot else "html"
    command_args: dict[str, object] = {
        "url": normalize_url(args.url),
        "output_mode": output_mode,
        "scroll_bottom": bool(args.scroll_bottom),
    }
    settle_ms = _settle_ms_from_args(args)
    if settle_ms is not None:
        command_args["settle_ms"] = settle_ms
    response = send_command(
        "run-start-read",
        command_args,
        start_if_needed=True,
    )
    data = dict(response.get("data") or {})
    if data.get("run_id"):
        data["poll"] = f"browser-cli run-status {data['run_id']} --json"
    return render_json_payload({"ok": True, "data": data, "meta": {"action": "read-async"}})


def _settle_ms_from_args(args: Namespace) -> int | None:
    raw = getattr(args, "settle_ms", None)
    if raw is None:
        return None
    settle_ms = int(raw)
    if settle_ms < 0:
        raise InvalidInputError("--settle-ms must be >= 0.")
    return settle_ms
