"""One-shot read orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from browser_cli.browser.models import BrowserLaunchConfig
from browser_cli.browser.session import BrowserSession
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


class ReadRunner:
    def __init__(self, chrome_environment: ChromeEnvironment | None = None) -> None:
        self._chrome_environment = chrome_environment

    async def run(self, request: ReadRequest) -> ReadResult:
        chrome_environment = self._chrome_environment or discover_chrome_environment()
        launch_config = BrowserLaunchConfig(
            executable_path=chrome_environment.executable_path,
            user_data_dir=chrome_environment.user_data_dir,
            profile_directory=chrome_environment.profile_directory,
            headless=True,
        )

        async with BrowserSession(launch_config) as browser:
            await browser.navigate(request.url)
            await browser.settle()
            if request.scroll_bottom:
                await browser.scroll_to_bottom()
                await browser.settle()

            if request.output_mode == "snapshot":
                body = await browser.capture_snapshot()
            else:
                body = await browser.capture_html()

        if not body.strip():
            raise EmptyContentError()
        used_fallback = getattr(chrome_environment, "source", "chrome") == "fallback"
        return ReadResult(
            body=body,
            used_fallback_profile=used_fallback,
            fallback_profile_dir=str(chrome_environment.user_data_dir) if used_fallback else None,
            fallback_reason=getattr(chrome_environment, "fallback_reason", None),
        )
