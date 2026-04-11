from __future__ import annotations

import time
from typing import Any

from browser_cli.refs.models import SnapshotInput

from ..models import TabState


class ExtensionDriverPageActionsMixin:
    async def new_tab(
        self,
        *,
        page_id: str,
        url: str | None = None,
        wait_until: str = "load",
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        session = await self._require_session()
        payload = await session.send_request(
            "open-tab",
            {
                "page_id": page_id,
                "url": url,
                "wait_until": wait_until,
                "timeout_seconds": timeout_seconds,
            },
        )
        tab_id = int(payload["tab_id"])
        self._page_to_tab[page_id] = tab_id
        self._tab_to_page[tab_id] = page_id
        self._active_page_id = page_id
        return {
            "page_id": page_id,
            "url": str(payload.get("url") or url or ""),
            "title": str(payload.get("title") or ""),
        }

    async def close_tab(self, page_id: str) -> dict[str, Any]:
        tab_id = self._require_tab_id(page_id)
        session = await self._require_session()
        payload = await session.send_request("close-tab", {"tab_id": tab_id})
        self._page_to_tab.pop(page_id, None)
        self._tab_to_page.pop(tab_id, None)
        if self._active_page_id == page_id:
            self._active_page_id = next(iter(self._page_to_tab.keys()), None)
        result = {
            "page_id": page_id,
            "closed": True,
            "url": str(payload.get("url") or ""),
            "title": str(payload.get("title") or ""),
        }
        video_paths = await self._materialize_video_artifacts(payload.get("_artifacts") or [])
        if video_paths:
            result["video_path"] = video_paths[0]
        return result

    async def list_tabs(self) -> list[TabState]:
        session = await self._require_session()
        payload = await session.send_request("list-tabs", {})
        results: list[TabState] = []
        for item in payload.get("tabs", []):
            try:
                tab_id = int(item["tab_id"])
            except Exception:
                continue
            page_id = self._tab_to_page.get(tab_id)
            if not page_id:
                continue
            results.append(
                TabState(
                    page_id=page_id,
                    url=str(item.get("url") or ""),
                    title=str(item.get("title") or ""),
                    active=bool(item.get("active")),
                )
            )
            if item.get("active"):
                self._active_page_id = page_id
        return results

    async def switch_tab(self, page_id: str) -> dict[str, Any]:
        tab_id = self._require_tab_id(page_id)
        session = await self._require_session()
        payload = await session.send_request("activate-tab", {"tab_id": tab_id})
        self._active_page_id = page_id
        return {
            "page_id": page_id,
            "url": str(payload.get("url") or ""),
            "title": str(payload.get("title") or ""),
        }

    async def get_page_summary(self, page_id: str) -> dict[str, Any]:
        tab_id = self._require_tab_id(page_id)
        session = await self._require_session()
        payload = await session.send_request("page-summary", {"tab_id": tab_id})
        return {
            "page_id": page_id,
            "url": str(payload.get("url") or ""),
            "title": str(payload.get("title") or ""),
        }

    async def get_page_info(self, page_id: str) -> dict[str, Any]:
        tab_id = self._require_tab_id(page_id)
        session = await self._require_session()
        payload = await session.send_request("page-info", {"tab_id": tab_id})
        return {"page_id": page_id, **payload}

    async def capture_html(self, page_id: str) -> dict[str, Any]:
        tab_id = self._require_tab_id(page_id)
        session = await self._require_session()
        payload = await session.send_request("capture-html", {"tab_id": tab_id})
        return {"page_id": page_id, "html": str(payload.get("html") or "")}

    async def capture_snapshot_input(
        self,
        page_id: str,
        *,
        interactive: bool = False,
        full_page: bool = True,
    ) -> SnapshotInput:
        tab_id = self._require_tab_id(page_id)
        session = await self._require_session()
        payload = await session.send_request(
            "capture-snapshot-input",
            {
                "tab_id": tab_id,
                "interactive": interactive,
                "full_page": full_page,
            },
        )
        return SnapshotInput(
            raw_snapshot=str(payload.get("raw_snapshot") or ""),
            captured_url=str(payload.get("captured_url") or ""),
            captured_at=float(payload.get("captured_at") or time.time()),
        )

    async def navigate(
        self,
        page_id: str,
        url: str,
        *,
        wait_until: str = "load",
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        tab_id = self._require_tab_id(page_id)
        session = await self._require_session()
        payload = await session.send_request(
            "navigate",
            {
                "tab_id": tab_id,
                "url": url,
                "wait_until": wait_until,
                "timeout_seconds": timeout_seconds,
            },
        )
        return {"page_id": page_id, "url": str(payload.get("url") or url), "title": str(payload.get("title") or "")}

    async def reload(
        self,
        page_id: str,
        *,
        wait_until: str = "load",
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        return await self._simple_page_command(
            page_id,
            "reload",
            {"wait_until": wait_until, "timeout_seconds": timeout_seconds},
        )

    async def go_back(self, page_id: str) -> dict[str, Any]:
        return await self._simple_page_command(page_id, "go-back", {})

    async def go_forward(self, page_id: str) -> dict[str, Any]:
        return await self._simple_page_command(page_id, "go-forward", {})

    async def resize(self, page_id: str, *, width: int, height: int) -> dict[str, Any]:
        payload = await self._page_command(page_id, "resize", {"width": width, "height": height})
        return {"page_id": page_id, "width": int(payload.get("width") or width), "height": int(payload.get("height") or height)}

    async def evaluate(self, page_id: str, code: str) -> dict[str, Any]:
        payload = await self._page_command(page_id, "eval", {"code": code})
        return {"page_id": page_id, "result": payload.get("result")}

    async def _simple_page_command(self, page_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload = await self._page_command(page_id, action, payload)
        return {"page_id": page_id, "url": str(payload.get("url") or ""), "title": str(payload.get("title") or "")}

    async def _page_command(self, page_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        tab_id = self._require_tab_id(page_id)
        session = await self._require_session()
        return await session.send_request(action, {"tab_id": tab_id, **payload})
