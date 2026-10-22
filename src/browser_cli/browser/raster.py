"""Capture painted viewport tiles without changing page layout or browser preferences."""

from __future__ import annotations

import base64
import io
import math
from typing import Any

from PIL import Image

from browser_cli.errors import OperationFailedError

PAINTABLE_VIEWPORT_JS = """() => ({
    width: document.documentElement.clientWidth,
    height: document.documentElement.clientHeight
})"""
_SCROLL_AND_PAINT_JS = """async position => {
    scrollTo({left: position.x, top: position.y, behavior: 'instant'});
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    return {x: scrollX, y: scrollY};
}"""
_MAX_PIXELS = 64_000_000
_MAX_TILES = 256


def _pixels(value: float) -> int:
    return max(1, math.floor(value + 0.5))


async def capture_tiled(
    page: Any,
    session: Any,
    clip: dict[str, float],
    *,
    geometry: dict[str, Any],
    paintable: dict[str, int],
    density: float,
    image_format: str,
) -> bytes:
    """Compose real painted pixels; the caller restores scroll in its finally block.

    Chrome's beyond-viewport capture can permanently suppress classic scrollbars.
    Keep it disabled for each tile. Clipping a large image without scrolling is
    insufficient: Chrome returns correctly sized images with unpainted content.
    """
    width, height = _pixels(clip["width"] * density), _pixels(clip["height"] * density)
    tile_width = max(1, math.floor(paintable["width"] * density))
    tile_height = max(1, math.floor(paintable["height"] * density))
    if (
        width * height > _MAX_PIXELS
        or math.ceil(width / tile_width) * math.ceil(height / tile_height) > _MAX_TILES
    ):
        raise OperationFailedError("Capture region is too large for viewport tile capture.")
    # A native, un-clipped frame carries the display ICC profile even on Chrome
    # versions that omit it on clipped PNGs. Preserve its raw pixel color space.
    profile = None
    native_pixels = (
        geometry["viewport_width"]
        * geometry["viewport_height"]
        * geometry["device_scale_factor"] ** 2
    )
    if native_pixels <= _MAX_PIXELS:
        reference = await session.send(
            "Page.captureScreenshot", {"format": "png", "fromSurface": True}
        )
        with Image.open(io.BytesIO(base64.b64decode(reference["data"]))) as image:
            profile = image.info.get("icc_profile")
    canvas = Image.new("RGBA", (width, height), "white")
    content_width = max(0, min(width, math.ceil((geometry["page_width"] - clip["x"]) * density)))
    content_height = max(0, min(height, math.ceil((geometry["page_height"] - clip["y"]) * density)))
    for top in range(0, content_height, tile_height):
        for left in range(0, content_width, tile_width):
            pixels_wide = min(tile_width, content_width - left)
            pixels_high = min(tile_height, content_height - top)
            x, y = clip["x"] + left / density, clip["y"] + top / density
            css_width, css_height = pixels_wide / density, pixels_high / density
            position = await page.evaluate(_SCROLL_AND_PAINT_JS, {"x": x, "y": y})
            if (
                x < position["x"] - 0.5
                or y < position["y"] - 0.5
                or x + css_width > position["x"] + paintable["width"] + 0.5
                or y + css_height > position["y"] + paintable["height"] + 0.5
            ):
                raise OperationFailedError(
                    "Requested capture region could not be painted without resizing the page."
                )
            result = await session.send(
                "Page.captureScreenshot",
                {
                    "format": "png",
                    "fromSurface": True,
                    "captureBeyondViewport": False,
                    "clip": {
                        "x": x,
                        "y": y,
                        "width": css_width,
                        "height": css_height,
                        "scale": clip["scale"],
                    },
                },
            )
            with Image.open(io.BytesIO(base64.b64decode(result["data"]))) as image:
                if image.width < pixels_wide or image.height < pixels_high:
                    raise OperationFailedError("Chrome returned an undersized screenshot tile.")
                if profile is None:
                    profile = image.info.get("icc_profile")
                canvas.paste(
                    image.convert("RGBA").crop((0, 0, pixels_wide, pixels_high)), (left, top)
                )
    output = io.BytesIO()
    metadata = {"icc_profile": profile} if profile else {}
    if image_format == "jpeg":
        canvas.convert("RGB").save(output, format="JPEG", quality=80, **metadata)
    else:
        canvas.save(output, format="PNG", **metadata)
    return output.getvalue()
