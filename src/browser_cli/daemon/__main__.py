"""Run the browser-cli daemon."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from browser_cli.constants import APP_HOME_ENV

from .server import BrowserDaemonServer


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--home")
    args, _unknown = parser.parse_known_args()
    if args.home:
        os.environ[APP_HOME_ENV] = args.home
    _configure_logging()
    asyncio.run(BrowserDaemonServer().serve())


if __name__ == "__main__":  # pragma: no cover
    main()
