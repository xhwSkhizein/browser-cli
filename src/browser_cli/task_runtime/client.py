"""Thin Browser CLI Python client for task execution."""

from __future__ import annotations

import asyncio
from typing import Any

from browser_cli.daemon.client import send_command
from browser_cli.profiles.discovery import ChromeEnvironment
from browser_cli.task_runtime.models import SnapshotResult
from browser_cli.task_runtime.read import ReadRequest, ReadResult, run_read_request


class BrowserCliTaskClient:
    def __init__(self, *, chrome_environment: ChromeEnvironment | None = None) -> None:
        self._chrome_environment = chrome_environment

    def invoke(self, action: str, **args: Any) -> dict[str, Any]:
        response = send_command(action, args)
        return dict(response.get("data") or {})

    def command(self, action: str, **args: Any) -> dict[str, Any]:
        return self.invoke(action, **args)

    def read(
        self,
        url: str,
        *,
        output_mode: str = "html",
        scroll_bottom: bool = False,
    ) -> ReadResult:
        return asyncio.run(
            run_read_request(
                ReadRequest(
                    url=url,
                    output_mode=output_mode,
                    scroll_bottom=scroll_bottom,
                ),
                chrome_environment=self._chrome_environment,
            )
        )

    def open(self, url: str) -> dict[str, Any]:
        return self.invoke("open", url=url).get("page", {})

    def search(self, query: str, *, engine: str = "duckduckgo") -> dict[str, Any]:
        return self.invoke("search", query=query, engine=engine).get("page", {})

    def snapshot(self, *, interactive: bool = False, full_page: bool = True) -> SnapshotResult:
        return SnapshotResult.from_payload(
            self.invoke("snapshot", interactive=interactive, full_page=full_page)
        )

    def html(self) -> str:
        return str(self.invoke("html").get("html") or "")

    def click(self, ref: str) -> dict[str, Any]:
        return self.invoke("click", ref=ref)

    def fill(self, ref: str, text: str, *, submit: bool = False) -> dict[str, Any]:
        return self.invoke("fill", ref=ref, text=text, submit=submit)

    def select(self, ref: str, text: str) -> dict[str, Any]:
        return self.invoke("select", ref=ref, text=text)

    def check(self, ref: str) -> dict[str, Any]:
        return self.invoke("check", ref=ref)

    def uncheck(self, ref: str) -> dict[str, Any]:
        return self.invoke("uncheck", ref=ref)

    def focus(self, ref: str) -> dict[str, Any]:
        return self.invoke("focus", ref=ref)

    def hover(self, ref: str) -> dict[str, Any]:
        return self.invoke("hover", ref=ref)

    def wait(self, seconds: float) -> dict[str, Any]:
        return self.invoke("wait", seconds=seconds)

    def wait_text(
        self, text: str, *, timeout: float = 5.0, gone: bool = False, exact: bool = False
    ) -> dict[str, Any]:
        return self.invoke("wait", seconds=timeout, text=text, gone=gone, exact=exact)

    def eval(self, code: str) -> Any:
        return self.invoke("eval", code=code).get("result")

    def eval_on(self, ref: str, code: str) -> Any:
        return self.invoke("eval-on", ref=ref, code=code).get("result")

    def verify_text(
        self, text: str, *, exact: bool = False, timeout: float = 5.0
    ) -> dict[str, Any]:
        return self.invoke("verify-text", text=text, exact=exact, timeout=timeout)

    def verify_state(self, ref: str, state: str) -> dict[str, Any]:
        return self.invoke("verify-state", ref=ref, state=state)

    def verify_value(self, ref: str, expected: str) -> dict[str, Any]:
        return self.invoke("verify-value", ref=ref, expected=expected)

    def screenshot(self, path: str, *, full_page: bool = False) -> dict[str, Any]:
        return self.invoke("screenshot", path=path, full_page=full_page)

    def close(self) -> dict[str, Any]:
        return self.invoke("close")
