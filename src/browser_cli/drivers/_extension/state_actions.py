from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from browser_cli.errors import OperationFailedError, TabNotFoundError

if TYPE_CHECKING:
    from browser_cli.extension import ExtensionHub


class ExtensionDriverStateMixin:
    _hub: ExtensionHub
    _page_to_tab: dict[str, int]
    _tab_to_page: dict[int, str]
    _active_page_id: str | None

    async def ensure_started(self) -> None:
        await self._hub.ensure_started()
        if self._hub.session is None:
            raise OperationFailedError(
                "Browser CLI extension is not connected.",
                error_code="EXTENSION_UNAVAILABLE",
            )

    async def stop(self) -> dict[str, Any]:
        closed_pages = sorted(self._page_to_tab.keys())
        session = self._hub.session
        payload: dict[str, Any] = {}
        cleanup_error: str | None = None
        if session is not None:
            try:
                payload = await session.send_request("workspace-close", {})
            except Exception as exc:
                cleanup_error = str(exc)
                payload = {}
        video_paths = await self._materialize_video_artifacts(payload.get("_artifacts") or [])
        self._page_to_tab.clear()
        self._tab_to_page.clear()
        self._active_page_id = None
        result = {
            "closed_pages": closed_pages,
            "extension_connected": session is not None,
            "video_paths": video_paths,
        }
        if cleanup_error:
            result["cleanup_error"] = cleanup_error
        return result

    async def workspace_status(self) -> dict[str, Any]:
        session = await self._require_session()
        payload = await session.send_request("workspace-status", {})
        return {
            "window_id": payload.get("window_id"),
            "tab_count": int(payload.get("tab_count") or 0),
            "managed_tab_count": int(payload.get("managed_tab_count") or 0),
            "binding_state": str(payload.get("binding_state") or "absent"),
        }

    async def rebuild_workspace_binding(self) -> dict[str, Any]:
        session = await self._require_session()
        payload = await session.send_request("workspace-rebuild-binding", {})
        self._page_to_tab.clear()
        self._tab_to_page.clear()
        self._active_page_id = None
        return {
            "rebuilt": bool(payload.get("rebuilt")),
            "workspace_window_state": {
                "window_id": payload.get("window_id"),
                "tab_count": int(payload.get("tab_count") or 0),
                "managed_tab_count": int(payload.get("managed_tab_count") or 0),
                "binding_state": str(payload.get("binding_state") or "absent"),
            },
        }

    async def health(self):
        session = self._hub.session
        if session is None:
            from ..models import DriverHealth

            return DriverHealth(name=self.name, available=False, details={"connected": False})
        hello = session.hello
        from ..models import DriverHealth

        return DriverHealth(
            name=self.name,
            available=hello.has_required_capabilities(),
            details={
                "connected": True,
                "extension_version": hello.extension_version,
                "browser_name": hello.browser_name,
                "browser_version": hello.browser_version,
                "capabilities": sorted(hello.capabilities),
                "capability_complete": hello.has_required_capabilities(),
                "missing_capabilities": hello.missing_required_capabilities(),
                "workspace_window_state": dict(hello.workspace_window_state),
                "extension_instance_id": hello.extension_instance_id,
            },
        )

    async def _require_session(self):
        await self.ensure_started()
        session = self._hub.session
        if session is None:
            raise OperationFailedError(
                "Browser CLI extension is not connected.", error_code="EXTENSION_UNAVAILABLE"
            )
        return session

    def _require_tab_id(self, page_id: str) -> int:
        tab_id = self._page_to_tab.get(page_id)
        if tab_id is None:
            raise TabNotFoundError()
        return tab_id

    @staticmethod
    def _resolve_output_path(path: str | None, *, page_id: str, suffix: str) -> Path:
        if not path:
            from browser_cli.constants import get_app_paths

            output = get_app_paths().artifacts_dir / f"{page_id}{suffix}"
            output.parent.mkdir(parents=True, exist_ok=True)
            return output.resolve()
        raw = Path(path).expanduser()
        if not raw.is_absolute():
            from browser_cli.constants import get_app_paths

            raw = (get_app_paths().artifacts_dir / raw).resolve()
        if raw.suffix.lower() != suffix:
            raw = raw.with_suffix(suffix)
        raw.parent.mkdir(parents=True, exist_ok=True)
        return raw
