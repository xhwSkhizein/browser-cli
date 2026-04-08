"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from browser_cli import __version__, exit_codes
from browser_cli.commands.read import run_read_command
from browser_cli.errors import BrowserCliError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="browser-cli")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    read_parser = subparsers.add_parser(
        "read",
        help="Read a rendered page as HTML or snapshot text.",
        description="Open a page, wait for render completion, and capture rendered output.",
    )
    read_parser.add_argument("url", help="Target page URL.")
    read_parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Return snapshot tree output instead of rendered HTML.",
    )
    read_parser.add_argument(
        "--scroll-bottom",
        action="store_true",
        help="Scroll to the bottom before capture to trigger lazy-loaded content.",
    )
    read_parser.set_defaults(handler=run_read_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else exit_codes.USAGE_ERROR
        return code

    if not hasattr(args, "handler"):
        parser.print_help()
        return exit_codes.USAGE_ERROR

    try:
        result = args.handler(args)
    except BrowserCliError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return exc.exit_code
    except KeyboardInterrupt:
        sys.stderr.write("Error: interrupted.\n")
        return exit_codes.TEMPORARY_FAILURE
    except Exception as exc:  # pragma: no cover - last-resort guard
        sys.stderr.write(f"Error: unexpected failure: {exc}\n")
        return exit_codes.INTERNAL_ERROR

    if result:
        sys.stdout.write(result)
    return exit_codes.SUCCESS


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

