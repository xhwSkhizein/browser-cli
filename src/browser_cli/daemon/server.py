"""Daemon server entrypoint."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time

from browser_cli import __version__
from browser_cli.constants import get_app_paths

from .app import BrowserDaemonApp
from .models import DaemonRequest, DaemonResponse
from .transport import DAEMON_RUNTIME_VERSION, ensure_run_dir, remove_run_info, safe_remove_socket, write_run_info

logger = logging.getLogger(__name__)


class BrowserDaemonServer:
    def __init__(self, app: BrowserDaemonApp | None = None) -> None:
        self._app = app or BrowserDaemonApp()
        self._server: asyncio.AbstractServer | None = None

    async def serve(self) -> None:
        app_paths = get_app_paths()
        logger.info("Starting Browser CLI daemon")
        loop = asyncio.get_running_loop()
        installed_signal_handlers: list[signal.Signals] = []
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            try:
                loop.add_signal_handler(sig, self._app.state.shutdown_event.set)
                installed_signal_handlers.append(sig)
            except (NotImplementedError, RuntimeError):
                pass
        ensure_run_dir()
        if app_paths.socket_path.exists():
            safe_remove_socket(app_paths.socket_path)
        try:
            await self._app.state.browser_service.ensure_extension_listener_started()
            self._server = await asyncio.start_unix_server(
                self._handle_client,
                path=str(app_paths.socket_path),
            )
            try:
                os.chmod(app_paths.socket_path, 0o600)
            except OSError:
                pass
            write_run_info(
                {
                    "transport": "unix",
                    "socket": str(app_paths.socket_path),
                    "pid": os.getpid(),
                    "pgid": os.getpgrp(),
                    "home": str(app_paths.home),
                    "started_at": time.time(),
                    "package_version": __version__,
                    "runtime_version": DAEMON_RUNTIME_VERSION,
                }
            )
            logger.info("Browser CLI daemon listening on %s", app_paths.socket_path)
            await self._app.state.shutdown_event.wait()
        finally:
            logger.info("Stopping Browser CLI daemon")
            if self._server is not None:
                self._server.close()
                await self._server.wait_closed()
                self._server = None
            await self._app.state.browser_service.stop()
            remove_run_info()
            try:
                safe_remove_socket(app_paths.socket_path)
            except FileNotFoundError:
                pass
            for sig in installed_signal_handlers:
                try:
                    loop.remove_signal_handler(sig)
                except Exception:
                    pass

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await reader.readline()
            if not raw:
                return
            payload = json.loads(raw.decode("utf-8"))
            request = DaemonRequest.from_dict(payload)
            response = await self._app.execute(request)
        except Exception as exc:  # pragma: no cover
            response = DaemonResponse.failure(
                error_code="DAEMON_PROTOCOL_ERROR",
                error_message=str(exc),
            )
        writer.write((json.dumps(response.to_dict()) + "\n").encode("utf-8"))
        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
