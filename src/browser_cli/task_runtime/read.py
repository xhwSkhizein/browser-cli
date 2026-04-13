"""Shared one-shot read orchestration for the task runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from browser_cli.daemon.client import send_command
from browser_cli.daemon.transport import probe_socket
from browser_cli.errors import EmptyContentError
from browser_cli.profiles.discovery import ChromeEnvironment, discover_chrome_environment


@dataclass(slots=True)
class ReadRequest:
    url: str
    output_mode: str
    scroll_bottom: bool = False


@dataclass(slots=True)
class ReadResult:
    body: str
    used_fallback_profile: bool = False
    fallback_profile_dir: str | None = None
    fallback_reason: str | None = None


def serialize_chrome_environment(chrome_environment: ChromeEnvironment) -> dict[str, str | None]:
    return {
        "executable_path": (
            str(chrome_environment.executable_path)
            if chrome_environment.executable_path is not None
            else None
        ),
        "user_data_dir": str(chrome_environment.user_data_dir),
        "profile_directory": chrome_environment.profile_directory,
        "profile_name": chrome_environment.profile_name,
        "source": chrome_environment.source,
        "fallback_reason": chrome_environment.fallback_reason,
    }


async def run_read_request(
    request: ReadRequest,
    *,
    chrome_environment: ChromeEnvironment | None = None,
) -> ReadResult:
    command_args = {
        "url": request.url,
        "output_mode": request.output_mode,
        "scroll_bottom": request.scroll_bottom,
    }
    if not probe_socket():
        resolved_environment = chrome_environment or discover_chrome_environment()
        command_args["chrome_environment"] = serialize_chrome_environment(resolved_environment)
    payload = await asyncio.to_thread(send_command, "read-page", command_args)
    body = str(payload.get("data", {}).get("body") or "")
    if not body.strip():
        raise EmptyContentError()
    used_fallback = bool(payload.get("data", {}).get("used_fallback_profile"))
    return ReadResult(
        body=body,
        used_fallback_profile=used_fallback,
        fallback_profile_dir=(
            str(payload.get("data", {}).get("fallback_profile_dir"))
            if used_fallback and payload.get("data", {}).get("fallback_profile_dir")
            else None
        ),
        fallback_reason=str(payload.get("data", {}).get("fallback_reason") or "") or None,
    )
