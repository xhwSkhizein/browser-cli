"""Run the browser-cli daemon."""

from __future__ import annotations

import asyncio

from .server import BrowserDaemonServer


def main() -> None:
    asyncio.run(BrowserDaemonServer().serve())


if __name__ == "__main__":  # pragma: no cover
    main()
