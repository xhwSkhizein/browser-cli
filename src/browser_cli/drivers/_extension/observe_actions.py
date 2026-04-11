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

    async def wait_for_network_record(
        self,
        page_id: str,
        *,
        url_contains: str | None = None,
        url_regex: str | None = None,
        method: str | None = None,
        status: int | None = None,
        resource_type: str | None = None,
        mime_contains: str | None = None,
        include_static: bool = False,
        timeout_seconds: float = 30.0,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "network-wait",
            {
                "url_contains": url_contains,
                "url_regex": url_regex,
                "method": method,
                "status": status,
                "resource_type": resource_type,
                "mime_contains": mime_contains,
                "include_static": include_static,
                "timeout_seconds": timeout_seconds,
            },
        )
        await self._materialize_network_body_artifacts(payload, page_id=page_id)
        return {"page_id": page_id, **payload}

    async def get_network_records(
        self,
        page_id: str,
        *,
        url_contains: str | None = None,
        url_regex: str | None = None,
        method: str | None = None,
        status: int | None = None,
        resource_type: str | None = None,
        mime_contains: str | None = None,
        include_static: bool = False,
        clear: bool = True,
    ) -> dict[str, object]:
        payload = await self._page_command(
            page_id,
            "network",
            {
                "url_contains": url_contains,
                "url_regex": url_regex,
                "method": method,
                "status": status,
                "resource_type": resource_type,
                "mime_contains": mime_contains,
                "include_static": include_static,
                "clear": clear,
            },
        )
        await self._materialize_network_body_artifacts(payload, page_id=page_id)
        return {"page_id": page_id, **payload}

    async def stop_network_capture(self, page_id: str) -> dict[str, object]:
        payload = await self._page_command(page_id, "network-stop", {})
        return {"page_id": page_id, **payload}

    async def _materialize_network_body_artifacts(self, payload: dict[str, object], *, page_id: str) -> None:
        artifacts = list(payload.get("_artifacts") or [])
        artifact_paths: dict[str, str] = {}
        for artifact in artifacts:
            if str(artifact.get("artifact_kind") or "") != "network-body":
                continue
            artifact_id = str(artifact.get("artifact_id") or "").strip()
            if not artifact_id:
                continue
            resolved = self._resolve_artifact_output_path(
                artifact,
                page_id=page_id,
                path=None,
                suffix="",
            )
            self._write_artifact_bytes(artifact, resolved)
            artifact_paths[artifact_id] = str(resolved)
        if "record" in payload and isinstance(payload.get("record"), dict):
            self._rewrite_network_body_path(payload["record"], artifact_paths)
        records = payload.get("records")
        if isinstance(records, list):
            for record in records:
                if isinstance(record, dict):
                    self._rewrite_network_body_path(record, artifact_paths)

    @staticmethod
    def _rewrite_network_body_path(record: dict[str, object], artifact_paths: dict[str, str]) -> None:
        body = record.get("body")
        if not isinstance(body, dict):
            return
        raw_path = str(body.get("path") or "")
        if not raw_path.startswith("artifact://"):
            return
        artifact_id = raw_path.removeprefix("artifact://")
        resolved_path = artifact_paths.get(artifact_id)
        if resolved_path:
            body["path"] = resolved_path

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
