from __future__ import annotations

from typing import Any

from browser_cli.refs.models import LocatorSpec


class ExtensionDriverLocatorActionsMixin:
    async def click(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]:
        await self._locator_command(page_id, "click", locator)
        return {"page_id": page_id, "ref": locator.ref, "action": "click"}

    async def double_click(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]:
        await self._locator_command(page_id, "double-click", locator)
        return {"page_id": page_id, "ref": locator.ref, "action": "double-click"}

    async def hover(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]:
        await self._locator_command(page_id, "hover", locator)
        return {"page_id": page_id, "ref": locator.ref, "action": "hover"}

    async def focus(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]:
        await self._locator_command(page_id, "focus", locator)
        return {"page_id": page_id, "ref": locator.ref, "action": "focus"}

    async def fill(
        self,
        page_id: str,
        locator: LocatorSpec,
        text: str,
        *,
        submit: bool = False,
    ) -> dict[str, Any]:
        await self._locator_command(page_id, "fill", locator, {"text": text, "submit": submit})
        return {"page_id": page_id, "ref": locator.ref, "filled": True, "submitted": submit}

    async def select_option(self, page_id: str, locator: LocatorSpec, text: str) -> dict[str, Any]:
        await self._locator_command(page_id, "select", locator, {"text": text})
        return {"page_id": page_id, "ref": locator.ref, "selected": text}

    async def list_options(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]:
        payload = await self._locator_command(page_id, "options", locator)
        return {"page_id": page_id, "ref": locator.ref, **payload}

    async def check(self, page_id: str, locator: LocatorSpec, *, checked: bool) -> dict[str, Any]:
        await self._locator_command(page_id, "check", locator, {"checked": checked})
        return {"page_id": page_id, "ref": locator.ref, "checked": checked}

    async def scroll_to(self, page_id: str, locator: LocatorSpec) -> dict[str, Any]:
        await self._locator_command(page_id, "scroll-to", locator)
        return {"page_id": page_id, "ref": locator.ref, "scrolled": True}

    async def drag(self, page_id: str, start_locator: LocatorSpec, end_locator: LocatorSpec) -> dict[str, Any]:
        payload = await self._page_command(
            page_id,
            "drag",
            {"start_locator": start_locator.to_dict(), "end_locator": end_locator.to_dict()},
        )
        return {
            "page_id": page_id,
            "start_ref": start_locator.ref,
            "end_ref": end_locator.ref,
            **payload,
        }

    async def upload(self, page_id: str, locator: LocatorSpec, file_path: str) -> dict[str, Any]:
        payload = await self._locator_command(page_id, "upload", locator, {"path": file_path})
        return {"page_id": page_id, "ref": locator.ref, **payload}

    async def evaluate_on(self, page_id: str, locator: LocatorSpec, code: str) -> dict[str, Any]:
        payload = await self._locator_command(page_id, "eval-on", locator, {"code": code})
        return {"page_id": page_id, "ref": locator.ref, "result": payload.get("result")}

    async def verify_state(self, page_id: str, *, locator: LocatorSpec, state: str) -> dict[str, Any]:
        payload = await self._locator_command(page_id, "verify-state", locator, {"state": state})
        return {"page_id": page_id, "ref": locator.ref, **payload}

    async def verify_value(self, page_id: str, *, locator: LocatorSpec, expected: str) -> dict[str, Any]:
        payload = await self._locator_command(page_id, "verify-value", locator, {"expected": expected})
        return {"page_id": page_id, "ref": locator.ref, **payload}

    async def _locator_command(
        self,
        page_id: str,
        action: str,
        locator: LocatorSpec,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._page_command(
            page_id,
            action,
            {"locator": locator.to_dict(), **(payload or {})},
        )
