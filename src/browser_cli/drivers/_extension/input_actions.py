from __future__ import annotations


class ExtensionDriverInputActionsMixin:
    async def type_text(self, page_id: str, text: str, *, submit: bool = False) -> dict[str, object]:
        payload = await self._page_command(page_id, "type", {"text": text, "submit": submit})
        return {"page_id": page_id, **payload}

    async def press_key(self, page_id: str, key: str) -> dict[str, object]:
        payload = await self._page_command(page_id, "press", {"key": key})
        return {"page_id": page_id, **payload}

    async def key_down(self, page_id: str, key: str) -> dict[str, object]:
        payload = await self._page_command(page_id, "key-down", {"key": key})
        return {"page_id": page_id, **payload}

    async def key_up(self, page_id: str, key: str) -> dict[str, object]:
        payload = await self._page_command(page_id, "key-up", {"key": key})
        return {"page_id": page_id, **payload}

    async def wheel(self, page_id: str, *, dx: int = 0, dy: int = 700) -> dict[str, object]:
        payload = await self._page_command(page_id, "scroll", {"dx": dx, "dy": dy})
        return {"page_id": page_id, **payload}

    async def mouse_move(self, page_id: str, *, x: int, y: int) -> dict[str, object]:
        payload = await self._page_command(page_id, "mouse-move", {"x": x, "y": y})
        return {"page_id": page_id, **payload}

    async def mouse_click(
        self,
        page_id: str,
        *,
        x: int,
        y: int,
        button: str = "left",
        count: int = 1,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "mouse-click",
            {"x": x, "y": y, "button": button, "count": count},
        )
        return {"page_id": page_id, **payload}

    async def mouse_drag(self, page_id: str, *, x1: int, y1: int, x2: int, y2: int) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "mouse-drag",
            {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        )
        return {"page_id": page_id, **payload}

    async def mouse_down(self, page_id: str, *, button: str = "left") -> dict[str, object]:
        payload = await self._page_command(page_id, "mouse-down", {"button": button})
        return {"page_id": page_id, **payload}

    async def mouse_up(self, page_id: str, *, button: str = "left") -> dict[str, object]:
        payload = await self._page_command(page_id, "mouse-up", {"button": button})
        return {"page_id": page_id, **payload}
