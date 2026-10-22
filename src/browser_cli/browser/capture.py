"""Capture geometry, validation and image metadata shared by browser drivers."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Any

from browser_cli.errors import InvalidInputError, OperationFailedError

PAGE_GEOMETRY_JS = """() => ({
    viewport_width: window.innerWidth,
    viewport_height: window.innerHeight,
    page_width: Math.max(document.body?.scrollWidth || 0, document.documentElement.scrollWidth),
    page_height: Math.max(document.body?.scrollHeight || 0, document.documentElement.scrollHeight),
    screen_width: window.screen.width,
    screen_height: window.screen.height,
    scroll_x: window.scrollX,
    scroll_y: window.scrollY,
    device_scale_factor: window.devicePixelRatio
})"""


def finite_number(value: Any, name: str, *, minimum: float = 0, maximum: float = 100_000) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidInputError(f"{name} must be a finite number.")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise InvalidInputError(f"{name} must be between {minimum} and {maximum}.")
    return float(value)


@dataclass(frozen=True)
class CaptureOptions:
    full_page: bool = False
    clip: dict[str, float] | None = None
    viewport: dict[str, int] | None = None
    device_scale_factor: float | None = None

    @classmethod
    def from_dict(cls, args: dict[str, Any]) -> CaptureOptions:
        full_page = args.get("full_page", False)
        if not isinstance(full_page, bool):
            raise InvalidInputError("full_page must be a boolean.")
        clip = args.get("clip")
        if clip is not None:
            if not isinstance(clip, dict) or set(clip) != {"x", "y", "width", "height"}:
                raise InvalidInputError("clip requires exactly x, y, width and height.")
            clip = {key: finite_number(value, f"clip.{key}") for key, value in clip.items()}
            if clip["width"] <= 0 or clip["height"] <= 0:
                raise InvalidInputError("clip width and height must be positive.")
            if full_page:
                raise InvalidInputError("clip and full_page cannot be combined.")
        width, height = args.get("viewport_width"), args.get("viewport_height")
        viewport = None
        if width is not None or height is not None:
            for value, name in ((width, "viewport_width"), (height, "viewport_height")):
                if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 16384:
                    raise InvalidInputError(
                        f"{name} must be an integer between 1 and 16384; supply both viewport dimensions."
                    )
            viewport = {"width": width, "height": height}
        dpr = args.get("device_scale_factor")
        if dpr is not None:
            dpr = finite_number(dpr, "device_scale_factor", minimum=0.1, maximum=8)
        return cls(full_page, clip, viewport, dpr)

    def capture_clip(self, geometry: dict[str, Any]) -> dict[str, float]:
        if self.clip is not None:
            rectangle = dict(self.clip)
        elif self.full_page:
            rectangle = {
                "x": 0.0,
                "y": 0.0,
                "width": geometry["page_width"],
                "height": geometry["page_height"],
            }
        else:
            rectangle = {
                "x": geometry["scroll_x"],
                "y": geometry["scroll_y"],
                "width": geometry["viewport_width"],
                "height": geometry["viewport_height"],
            }
        dpr = geometry["device_scale_factor"]
        rectangle["scale"] = (self.device_scale_factor or dpr) / dpr
        return rectangle

    def metadata(
        self, geometry: dict[str, Any], *, before: dict[str, Any], after: dict[str, Any]
    ) -> dict[str, Any]:
        rectangle = self.capture_clip(geometry)
        return {
            "page_range": "clip"
            if self.clip is not None
            else "full"
            if self.full_page
            else "viewport",
            "clip": {key: rectangle[key] for key in ("x", "y", "width", "height")},
            "viewport": {
                "width": geometry["viewport_width"],
                "height": geometry["viewport_height"],
            },
            "device_scale_factor": self.device_scale_factor or geometry["device_scale_factor"],
            "page_dimensions_unchanged": before == after,
            "before": before,
            "after": after,
        }


def image_dimensions(content: bytes) -> dict[str, int]:
    if len(content) >= 24 and content[:8] == b"\x89PNG\r\n\x1a\n" and content[12:16] == b"IHDR":
        width, height = struct.unpack(">II", content[16:24])
        return {"width": width, "height": height}
    if content[:2] == b"\xff\xd8":
        offset = 2
        while offset + 8 < len(content):
            if content[offset] != 0xFF:
                break
            marker = content[offset + 1]
            offset += 2
            if marker in {0xD8, 0xD9}:
                continue
            length = int.from_bytes(content[offset : offset + 2], "big")
            if marker in {0xC0, 0xC1, 0xC2}:
                height, width = struct.unpack(">HH", content[offset + 3 : offset + 7])
                return {"width": width, "height": height}
            if length < 2:
                break
            offset += length
    raise OperationFailedError("Browser returned an invalid screenshot image.")
