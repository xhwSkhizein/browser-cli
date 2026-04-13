"""Read command handler."""

from __future__ import annotations

import sys
from argparse import Namespace

from browser_cli.outputs.render import render_output
from browser_cli.task_runtime import BrowserCliTaskClient


def normalize_url(url: str) -> str:
    if "://" in url:
        return url
    return f"https://{url}"


def run_read_command(args: Namespace) -> str:
    client = BrowserCliTaskClient()
    result = client.read(
        normalize_url(args.url),
        output_mode="snapshot" if args.snapshot else "html",
        scroll_bottom=bool(args.scroll_bottom),
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
