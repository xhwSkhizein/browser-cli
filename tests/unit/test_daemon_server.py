from __future__ import annotations

import asyncio
from pathlib import Path

from browser_cli.constants import APP_HOME_ENV, get_app_paths
from browser_cli.daemon.server import BrowserDaemonServer


class _FakeBrowserService:
    def __init__(self) -> None:
        self.listener_started = False
        self.stopped = False

    async def ensure_extension_listener_started(self) -> None:
        self.listener_started = True

    async def stop(self) -> dict:
        self.stopped = True
        return {}


class _FakeState:
    def __init__(self) -> None:
        self.browser_service = _FakeBrowserService()
        self.shutdown_event = asyncio.Event()


class _FakeApp:
    def __init__(self) -> None:
        self.state = _FakeState()


def test_daemon_server_starts_extension_listener_before_waiting(
    monkeypatch, tmp_path: Path
) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / ".browser-cli-runtime"))
        app = _FakeApp()
        server = BrowserDaemonServer(app=app)  # type: ignore[arg-type]

        async def _trigger_shutdown() -> None:
            while not app.state.browser_service.listener_started:
                await asyncio.sleep(0)
            await asyncio.sleep(0.01)
            app.state.shutdown_event.set()

        await asyncio.gather(server.serve(), _trigger_shutdown())

        assert app.state.browser_service.listener_started is True
        assert app.state.browser_service.stopped is True
        assert not get_app_paths().socket_path.exists()

    asyncio.run(_scenario())
