from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from browser_cli.browser.capture import CaptureOptions, image_dimensions
from browser_cli.errors import ExtensionCapabilityIncompleteError, OperationFailedError


class ExtensionDriverArtifactActionsMixin:
    async def screenshot(
        self,
        page_id: str,
        *,
        path: str,
        full_page: bool = False,
        clip: dict[str, float] | None = None,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
        device_scale_factor: float | None = None,
    ) -> dict[str, Any]:
        CaptureOptions.from_dict(
            {
                "full_page": full_page,
                "clip": clip,
                "viewport_width": viewport_width,
                "viewport_height": viewport_height,
                "device_scale_factor": device_scale_factor,
            }
        )
        session = await self._require_session()
        if "screenshot-controls" not in session.hello.capabilities:
            raise ExtensionCapabilityIncompleteError(
                "Reload the Browser CLI extension to enable screenshot-controls before capturing screenshots."
            )
        suffix = Path(path).suffix.lower()
        suffix = suffix if suffix in {".jpg", ".jpeg"} else ".png"
        payload = await self._page_command(
            page_id,
            "screenshot",
            {
                "full_page": full_page,
                "format": "jpeg" if suffix != ".png" else "png",
                "clip": clip,
                "viewport_width": viewport_width,
                "viewport_height": viewport_height,
                "device_scale_factor": device_scale_factor,
            },
        )
        capture = payload.get("capture")
        if (
            not isinstance(capture, dict)
            or capture.get("page_dimensions_unchanged") is not True
            or capture.get("before") != capture.get("after")
        ):
            raise OperationFailedError(
                "Extension did not confirm that page geometry was restored; screenshot was not saved."
            )
        artifacts = [
            item
            for item in payload.get("_artifacts", [])
            if item.get("artifact_kind") == "screenshot"
        ]
        content = (
            artifacts[0].get("content")
            if artifacts
            else base64.b64decode(payload.get("data_base64", ""))
        )
        if not isinstance(content, bytes | bytearray):
            raise OperationFailedError("Extension screenshot is missing image bytes.")
        screenshot_size = image_dimensions(bytes(content))
        output_path = await self._materialize_single_artifact(
            payload,
            page_id=page_id,
            path=path,
            suffix=suffix,
            artifact_kind="screenshot",
            inline_key="data_base64",
        )
        return {
            "page_id": page_id,
            "path": output_path,
            "full_page": full_page,
            "capture": capture,
            "screenshot_size": screenshot_size,
        }

    async def save_pdf(self, page_id: str, *, path: str) -> dict[str, Any]:
        payload = await self._page_command(page_id, "pdf", {})
        output_path = await self._materialize_single_artifact(
            payload,
            page_id=page_id,
            path=path,
            suffix=".pdf",
            artifact_kind="pdf",
            inline_key="data_base64",
        )
        return {"page_id": page_id, "path": output_path}

    async def start_tracing(
        self,
        page_id: str,
        *,
        screenshots: bool = True,
        snapshots: bool = True,
        sources: bool = False,
    ) -> dict[str, Any]:
        payload = await self._page_command(
            page_id,
            "trace-start",
            {"screenshots": screenshots, "snapshots": snapshots, "sources": sources},
        )
        return {"page_id": page_id, **payload}

    async def add_trace_chunk(self, page_id: str, *, title: str | None = None) -> dict[str, Any]:
        payload = await self._page_command(page_id, "trace-chunk", {"title": title})
        return {"page_id": page_id, **payload}

    async def stop_tracing(self, page_id: str, *, path: str | None = None) -> dict[str, Any]:
        payload = await self._page_command(page_id, "trace-stop", {"path": path})
        output_path = await self._materialize_single_artifact(
            payload,
            page_id=page_id,
            path=path,
            suffix=".zip",
            artifact_kind="trace",
        )
        return {"page_id": page_id, "path": output_path}

    async def start_video(
        self, page_id: str, *, width: int | None = None, height: int | None = None
    ) -> dict[str, Any]:
        payload = await self._page_command(
            page_id, "video-start", {"width": width, "height": height}
        )
        return {"page_id": page_id, **payload}

    async def stop_video(self, page_id: str, *, path: str | None = None) -> dict[str, Any]:
        payload = await self._page_command(page_id, "video-stop", {"path": path})
        return {"page_id": page_id, **payload}

    async def _materialize_single_artifact(
        self,
        payload: dict[str, Any],
        *,
        page_id: str,
        path: str | None,
        suffix: str,
        artifact_kind: str,
        inline_key: str | None = None,
    ) -> str:
        artifacts = list(payload.get("_artifacts") or [])
        if artifacts:
            for artifact in artifacts:
                if str(artifact.get("artifact_kind") or "") != artifact_kind:
                    continue
                resolved = self._resolve_artifact_output_path(
                    artifact,
                    page_id=page_id,
                    path=path,
                    suffix=suffix,
                )
                self._write_artifact_bytes(artifact, resolved)
                return str(resolved)
        if inline_key and payload.get(inline_key):
            output_path = self._resolve_output_path(path, page_id=page_id, suffix=suffix)
            output_path.write_bytes(
                base64.b64decode(str(payload.get(inline_key) or "").encode("ascii"))
            )
            return str(output_path)
        if path:
            return str(self._resolve_output_path(path, page_id=page_id, suffix=suffix))
        raise RuntimeError(f"Expected extension artifact kind {artifact_kind}.")

    async def _materialize_video_artifacts(self, artifacts: list[dict[str, Any]]) -> list[str]:
        paths: list[str] = []
        for artifact in artifacts:
            if str(artifact.get("artifact_kind") or "") != "video":
                continue
            page_id = str(artifact.get("page_id") or "page")
            resolved = self._resolve_artifact_output_path(
                artifact,
                page_id=page_id,
                path=str((artifact.get("metadata") or {}).get("requested_path") or "").strip()
                or None,
                suffix=".webm",
            )
            self._write_artifact_bytes(artifact, resolved)
            paths.append(str(resolved))
        return paths

    def _resolve_artifact_output_path(
        self,
        artifact: dict[str, Any],
        *,
        page_id: str,
        path: str | None,
        suffix: str,
    ):
        if path:
            return self._resolve_output_path(path, page_id=page_id, suffix=suffix)
        metadata = dict(artifact.get("metadata") or {})
        requested = str(metadata.get("requested_path") or "").strip()
        if requested:
            return self._resolve_output_path(requested, page_id=page_id, suffix=suffix)
        filename = str(artifact.get("filename") or "").strip()
        if filename:
            return self._resolve_output_path(filename, page_id=page_id, suffix=suffix)
        return self._resolve_output_path(None, page_id=page_id, suffix=suffix)

    @staticmethod
    def _write_artifact_bytes(artifact: dict[str, Any], output_path) -> None:
        content = artifact.get("content")
        if not isinstance(content, bytes | bytearray):
            raise RuntimeError("Extension artifact payload is missing binary content.")
        output_path.write_bytes(bytes(content))
