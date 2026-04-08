"""Read command handler."""

from __future__ import annotations

import asyncio
from argparse import Namespace

from browser_cli.outputs.render import render_output
from browser_cli.runtime.read_runner import ReadRequest, ReadRunner


def normalize_url(url: str) -> str:
    if "://" in url:
        return url
    return f"https://{url}"


def run_read_command(args: Namespace) -> str:
    request = ReadRequest(
        url=normalize_url(args.url),
        output_mode="snapshot" if args.snapshot else "html",
        scroll_bottom=bool(args.scroll_bottom),
    )
    runner = ReadRunner()
    result = asyncio.run(runner.run(request))
    return render_output(result.body)
