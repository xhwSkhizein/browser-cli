from __future__ import annotations


class ExtensionDriverDialogActionsMixin:
    async def setup_dialog_handler(
        self,
        page_id: str,
        *,
        default_action: str = "accept",
        default_prompt_text: str | None = None,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "dialog-setup",
            {"action": default_action, "text": default_prompt_text},
        )
        return {"page_id": page_id, **payload}

    async def handle_dialog(
        self,
        page_id: str,
        *,
        accept: bool,
        prompt_text: str | None = None,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "dialog",
            {"dismiss": not accept, "text": prompt_text},
        )
        return {"page_id": page_id, **payload}

    async def remove_dialog_handler(self, page_id: str) -> dict[str, object]:
        payload = await self._page_command(page_id, "dialog-remove", {})
        return {"page_id": page_id, **payload}
