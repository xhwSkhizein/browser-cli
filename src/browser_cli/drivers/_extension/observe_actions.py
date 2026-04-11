from __future__ import annotations

import json
from pathlib import Path


class ExtensionDriverObserveActionsMixin:
    async def wait(
        self,
        page_id: str,
        *,
        seconds: float | None = None,
        text: str | None = None,
        gone: bool = False,
        exact: bool = False,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "wait",
            {
                "seconds": seconds,
                "text": text,
                "gone": gone,
                "exact": exact,
            },
        )
        return {"page_id": page_id, **payload}

    async def wait_for_network_idle(self, page_id: str, *, timeout_seconds: float = 30.0) -> dict[str, object]:
        payload = await self._page_command(page_id, "wait-network", {"timeout_seconds": timeout_seconds})
        return {"page_id": page_id, **payload}

    async def start_console_capture(self, page_id: str) -> dict[str, object]:
        payload = await self._page_command(page_id, "console-start", {})
        return {"page_id": page_id, **payload}

    async def get_console_messages(
        self,
        page_id: str,
        *,
        message_type: str | None = None,
        clear: bool = True,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "console-get",
            {"message_type": message_type, "clear": clear},
        )
        return {"page_id": page_id, **payload}

    async def stop_console_capture(self, page_id: str) -> dict[str, object]:
        payload = await self._page_command(page_id, "console-stop", {})
        return {"page_id": page_id, **payload}

    async def start_network_capture(self, page_id: str) -> dict[str, object]:
        payload = await self._page_command(page_id, "network-start", {})
        return {"page_id": page_id, **payload}

    async def get_network_requests(
        self,
        page_id: str,
        *,
        include_static: bool = False,
        clear: bool = True,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "network-get",
            {"include_static": include_static, "clear": clear},
        )
        return {"page_id": page_id, **payload}

    async def stop_network_capture(self, page_id: str) -> dict[str, object]:
        payload = await self._page_command(page_id, "network-stop", {})
        return {"page_id": page_id, **payload}

    async def get_cookies(
        self,
        page_id: str,
        *,
        name: str | None = None,
        domain: str | None = None,
        path: str | None = None,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "cookies-get",
            {"name": name, "domain": domain, "path": path},
        )
        return {"page_id": page_id, **payload}

    async def set_cookie(
        self,
        page_id: str,
        *,
        name: str,
        value: str,
        domain: str | None = None,
        path: str = "/",
        expires: float | None = None,
        http_only: bool = False,
        secure: bool = False,
        same_site: str | None = None,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "cookie-set",
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "expires": expires,
                "http_only": http_only,
                "secure": secure,
                "same_site": same_site,
            },
        )
        return {"page_id": page_id, **payload}

    async def clear_cookies(
        self,
        page_id: str,
        *,
        name: str | None = None,
        domain: str | None = None,
        path: str | None = None,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "cookies-clear",
            {"name": name, "domain": domain, "path": path},
        )
        return {"page_id": page_id, **payload}

    async def save_storage_state(self, page_id: str, *, path: str | None = None) -> dict[str, object]:
        payload = await self._page_command(page_id, "storage-get", {})
        output_path = self._resolve_output_path(path, page_id=page_id, suffix=".json")
        output_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        return {"page_id": page_id, "path": str(output_path)}

    async def load_storage_state(self, page_id: str, *, path: str) -> dict[str, object]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        result = await self._page_command(page_id, "storage-set", payload)
        return {"page_id": page_id, **result}

    async def verify_text(
        self,
        page_id: str,
        *,
        text: str,
        exact: bool = False,
        timeout_seconds: float = 5.0,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "verify-text",
            {"text": text, "exact": exact, "timeout_seconds": timeout_seconds},
        )
        return {"page_id": page_id, **payload}

    async def verify_url(self, page_id: str, *, expected: str, exact: bool = False) -> dict[str, object]:
        payload = await self._page_command(page_id, "verify-url", {"expected": expected, "exact": exact})
        return {"page_id": page_id, **payload}

    async def verify_title(self, page_id: str, *, expected: str, exact: bool = False) -> dict[str, object]:
        payload = await self._page_command(page_id, "verify-title", {"expected": expected, "exact": exact})
        return {"page_id": page_id, **payload}

    async def verify_visible(
        self,
        page_id: str,
        *,
        role: str,
        name: str,
        timeout_seconds: float = 5.0,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "verify-visible",
            {"role": role, "name": name, "timeout_seconds": timeout_seconds},
        )
        return {"page_id": page_id, **payload}
