"""Cancellation discards only the interrupted extension request's artifacts."""

from __future__ import annotations

import asyncio
import json

import pytest

from browser_cli.extension.protocol import ExtensionArtifactBegin, ExtensionHello
from browser_cli.extension.session import ExtensionSession


def test_cancelled_extension_wait_discards_buffers_and_ignores_late_artifacts():
    async def scenario():
        sent = []

        class Socket:
            closed = False

            async def send(self, value):
                sent.append(json.loads(value))

        session = ExtensionSession(Socket(), ExtensionHello.from_message({}))
        running = asyncio.create_task(session.send_request("screenshot", {}))
        peer = asyncio.create_task(session.send_request("eval", {}))
        try:
            while len(sent) < 2:
                await asyncio.sleep(0)
            request_id = sent[0]["id"]
            peer_id = sent[1]["id"]
            begin = ExtensionArtifactBegin(
                request_id, "artifact", "screenshot", "image/png", "base64"
            )
            session.begin_artifact(begin)
            session.append_response_chunk(
                {"id": request_id, "index": 0, "chunk": '{"ok":', "final": False}
            )
            running.cancel()
            with pytest.raises(asyncio.CancelledError):
                await running
            assert list(session._pending) == [peer_id]
            assert session._artifact_buffers == {}
            assert session._response_buffers == {}
            assert session._completed_artifacts == {}
            session.begin_artifact(begin)
            assert session._artifact_buffers == {}
            assert list(session._pending) == [peer_id]
        finally:
            for task in (running, peer):
                task.cancel()
            await asyncio.gather(running, peer, return_exceptions=True)

    asyncio.run(scenario())
