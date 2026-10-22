from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from tests.integration.test_capture_context_batch import runtime

from browser_cli.constants import get_app_paths


@pytest.mark.parametrize("hashed_socket", [False, True])
def test_capture_runtime_listener_supports_missing_runtime_directory(monkeypatch, hashed_socket):
    with TemporaryDirectory(prefix="bcli-", dir="/tmp") as folder:
        home = Path(folder) / ("long-home-" * 15 if hashed_socket else "runtime")
        monkeypatch.setenv("BROWSER_CLI_HOME", str(home))
        path = get_app_paths().socket_path
        assert (path.parent != home / "run") is hashed_socket
        assert not (home / "run").exists()
        loop = asyncio.new_event_loop()
        browser_runtime = SimpleNamespace(loop=loop, app=object(), socket=path)
        fixture = runtime.__wrapped__(browser_runtime)
        try:
            assert next(fixture) is browser_runtime
            assert path.is_socket()
        finally:
            fixture.close()
            loop.close()
        assert not path.exists()
