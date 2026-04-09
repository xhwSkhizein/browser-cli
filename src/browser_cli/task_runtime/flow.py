"""Higher-level task runtime flow helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from browser_cli.task_runtime.client import BrowserCliTaskClient
from browser_cli.task_runtime.models import FlowContext, SnapshotResult


class Flow:
    def __init__(
        self,
        *,
        client: BrowserCliTaskClient | None = None,
        context: FlowContext,
    ) -> None:
        self.client = client or BrowserCliTaskClient()
        self.context = context
        self._last_snapshot: SnapshotResult | None = None

    @property
    def artifacts_dir(self) -> Path:
        self.context.artifacts_dir.mkdir(parents=True, exist_ok=True)
        return self.context.artifacts_dir

    def open(self, url: str) -> dict[str, Any]:
        return self.client.open(url)

    def command(self, action: str, **args: Any) -> dict[str, Any]:
        return self.client.command(action, **args)

    def search(self, query: str, *, engine: str = "duckduckgo") -> dict[str, Any]:
        return self.client.search(query, engine=engine)

    def snapshot(self, *, interactive: bool = False, full_page: bool = True) -> SnapshotResult:
        self._last_snapshot = self.client.snapshot(interactive=interactive, full_page=full_page)
        return self._last_snapshot

    def last_snapshot(self) -> SnapshotResult:
        if self._last_snapshot is None:
            self._last_snapshot = self.snapshot()
        return self._last_snapshot

    def snapshot_find(self, *, role: str, name: str, nth: int = 0, refresh: bool = False) -> str:
        snapshot = self.snapshot() if refresh or self._last_snapshot is None else self._last_snapshot
        return snapshot.find_ref(role=role, name=name, nth=nth)

    def click(self, ref: str) -> dict[str, Any]:
        return self.client.click(ref)

    def fill(self, ref: str, text: str, *, submit: bool = False) -> dict[str, Any]:
        return self.client.fill(ref, text, submit=submit)

    def select(self, ref: str, text: str) -> dict[str, Any]:
        return self.client.select(ref, text)

    def check(self, ref: str) -> dict[str, Any]:
        return self.client.check(ref)

    def uncheck(self, ref: str) -> dict[str, Any]:
        return self.client.uncheck(ref)

    def focus(self, ref: str) -> dict[str, Any]:
        return self.client.focus(ref)

    def hover(self, ref: str) -> dict[str, Any]:
        return self.client.hover(ref)

    def wait(self, seconds: float) -> dict[str, Any]:
        return self.client.wait(seconds)

    def wait_text(self, text: str, *, timeout: float = 5.0, gone: bool = False, exact: bool = False) -> dict[str, Any]:
        return self.client.wait_text(text, timeout=timeout, gone=gone, exact=exact)

    def html(self) -> str:
        return self.client.html()

    def eval(self, code: str) -> Any:
        return self.client.eval(code)

    def eval_on(self, ref: str, code: str) -> Any:
        return self.client.eval_on(ref, code)

    def verify_text(self, text: str, *, exact: bool = False, timeout: float = 5.0) -> bool:
        return bool(self.client.verify_text(text, exact=exact, timeout=timeout).get("passed"))

    def verify_state(self, ref: str, state: str) -> bool:
        return bool(self.client.verify_state(ref, state).get("passed"))

    def verify_value(self, ref: str, expected: str) -> bool:
        return bool(self.client.verify_value(ref, expected).get("passed"))

    def scroll_until_stable(
        self,
        *,
        max_rounds: int = 10,
        wait_seconds: float = 2.0,
        confirm_rounds: int = 2,
    ) -> dict[str, Any]:
        stable_rounds = 0
        history: list[dict[str, Any]] = []
        for index in range(1, max_rounds + 1):
            before = self.eval(
                """() => ({
                    scrollHeight: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
                    scrollY: window.scrollY,
                    viewportHeight: window.innerHeight
                })"""
            )
            self.eval(
                """() => {
                    const h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
                    window.scrollTo(0, h);
                    return h;
                }"""
            )
            self.wait(wait_seconds)
            after = self.eval(
                """() => ({
                    scrollHeight: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
                    scrollY: window.scrollY,
                    viewportHeight: window.innerHeight,
                    atBottom: window.innerHeight + window.scrollY >= Math.max(document.body.scrollHeight, document.documentElement.scrollHeight) - 4
                })"""
            )
            round_result = {"round": index, "before": before, "after": after}
            history.append(round_result)
            if after["atBottom"] and after["scrollHeight"] <= before["scrollHeight"]:
                stable_rounds += 1
                if stable_rounds >= confirm_rounds:
                    return {"stabilized": True, "rounds": history}
            else:
                stable_rounds = 0
        return {"stabilized": False, "rounds": history}

    def write_text_artifact(self, relative_path: str, content: str) -> Path:
        output_path = (self.artifacts_dir / relative_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        return output_path

    def write_json_artifact(self, relative_path: str, payload: Any) -> Path:
        output_path = (self.artifacts_dir / relative_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path

    def screenshot(self, relative_path: str, *, full_page: bool = False) -> Path:
        output_path = (self.artifacts_dir / relative_path).resolve()
        self.client.screenshot(str(output_path), full_page=full_page)
        return output_path

    def close(self) -> dict[str, Any]:
        return self.client.close()
