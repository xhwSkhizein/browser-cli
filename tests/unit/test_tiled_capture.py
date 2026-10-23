from __future__ import annotations

import asyncio
import base64
import io
import threading

import pytest
from PIL import Image, ImageCms, ImageDraw
from tests.unit.test_capture_controls import CapturePage

from browser_cli.browser.capture import PAGE_GEOMETRY_JS
from browser_cli.browser.service import BrowserService
from browser_cli.errors import OperationFailedError

PROFILE = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


class ScrollbarCapturePage(CapturePage):
    def __init__(self, *, fail_tile=False):
        super().__init__()
        self.viewport_size = {"width": 800, "height": 600}
        self.hidden = False
        self.fail_tile = fail_tile
        self.tiles = []

        async def send(method, params):
            if method != "Page.captureScreenshot":
                return {}
            clip = params.get("clip") or {
                "x": 0,
                "y": self.position["y"],
                "width": 800,
                "height": 600,
                "scale": 1,
            }
            if params.get("captureBeyondViewport"):
                self.hidden = True
            elif "clip" in params:
                self.tiles.append(clip)
                if self.fail_tile and len(self.tiles) == 2:
                    raise RuntimeError("tile failed")
            scale = clip.get("scale", 1)
            size = (round(clip["width"] * scale), round(clip["height"] * scale))
            image = Image.new("RGB", size, "white")
            # Only painted content is available without beyond-viewport capture.
            bottom = max(clip["y"], 2200)
            if bottom < clip["y"] + clip["height"] and (
                params.get("captureBeyondViewport") or bottom < self.position["y"] + 600
            ):
                ImageDraw.Draw(image).rectangle(
                    (
                        0,
                        round((bottom - clip["y"]) * scale),
                        min(size[0] - 1, round(200 * scale)),
                        size[1] - 1,
                    ),
                    fill="red",
                )
            output = io.BytesIO()
            image.save(
                output, format="PNG", **({"icc_profile": PROFILE} if "clip" not in params else {})
            )
            return {"data": base64.b64encode(output.getvalue()).decode()}

        self.cdp.send.side_effect = send

    async def evaluate(self, script, arg=None):
        if script == PAGE_GEOMETRY_JS:
            return {
                "viewport_width": 800,
                "viewport_height": 600,
                "page_width": 800 if self.hidden else 785,
                "page_height": 2400,
                "scroll_x": self.position["x"],
                "scroll_y": self.position["y"],
                "device_scale_factor": 1,
            }
        if "document.documentElement.clientWidth" in script:
            if "width:" in script:
                return {"width": 785, "height": 600}
            return True
        if arg is not None:
            self.position = {"x": 0, "y": min(max(arg["y"], 0), 1800)}
            if "requestAnimationFrame" in script:
                return dict(self.position)
        return True


@pytest.mark.parametrize("suffix,density", [("png", 1), ("jpg", 2)])
def test_classic_scrollbar_capture_keeps_geometry_and_real_bottom_pixels(tmp_path, suffix, density):
    page = ScrollbarCapturePage()
    service = BrowserService()
    service._pages["page"] = page
    output = tmp_path / f"full.{suffix}"
    result = asyncio.run(
        service.screenshot("page", path=str(output), full_page=True, device_scale_factor=density)
    )
    assert result["capture"]["before"] == result["capture"]["after"]
    assert page.position == {"x": 0, "y": 300}
    assert page.viewport_changes == []
    assert not page.hidden
    assert len(page.tiles) == 4
    with Image.open(output) as image:
        assert image.size == (785 * density, 2400 * density)
        assert image.info["icc_profile"] == PROFILE
        pixel = image.convert("RGB").getpixel((10 * density, 2300 * density))
        assert abs(pixel[0] - 255) <= 3 and pixel[1] <= 3 and pixel[2] <= 3


def test_failed_tile_restores_scroll_and_does_not_save_partial_image(tmp_path):
    page = ScrollbarCapturePage(fail_tile=True)
    service = BrowserService()
    service._pages["page"] = page
    output = tmp_path / "partial.png"
    with pytest.raises(RuntimeError, match="tile failed"):
        asyncio.run(service.screenshot("page", path=str(output), full_page=True))
    assert page.position == {"x": 0, "y": 300}
    assert page.viewport_changes == []
    assert not output.exists()


def test_oversized_tile_capture_fails_before_allocating_or_scrolling(tmp_path):
    page = ScrollbarCapturePage()
    service = BrowserService()
    service._pages["page"] = page
    output = tmp_path / "huge.png"
    with pytest.raises(OperationFailedError, match="too large"):
        asyncio.run(
            service.screenshot(
                "page", path=str(output), clip={"x": 0, "y": 0, "width": 100000, "height": 100000}
            )
        )
    assert page.tiles == []
    assert page.position == {"x": 0, "y": 300}
    assert not output.exists()


@pytest.mark.parametrize("suffix", ["png", "jpg"])
def test_final_image_conversion_and_encoding_run_outside_event_loop(tmp_path, monkeypatch, suffix):
    loop_thread = threading.get_ident()
    save = Image.Image.save
    convert = Image.Image.convert
    encoded = []
    converted = []

    def checked_convert(image, *args, **kwargs):
        if image.size == (785, 2400):
            converted.append(threading.get_ident())
        return convert(image, *args, **kwargs)

    def checked_save(image, fp, *args, **kwargs):
        if image.size == (785, 2400):
            encoded.append(threading.get_ident())
            assert threading.get_ident() != loop_thread
            assert kwargs["icc_profile"] == PROFILE
            assert kwargs["format"] == ("JPEG" if suffix == "jpg" else "PNG")
            if suffix == "jpg":
                assert kwargs["quality"] == 80
        return save(image, fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "convert", checked_convert)
    monkeypatch.setattr(Image.Image, "save", checked_save)
    service = BrowserService()
    service._pages["page"] = ScrollbarCapturePage()
    output = tmp_path / f"threaded.{suffix}"
    asyncio.run(service.screenshot("page", path=str(output), full_page=True))
    assert len(encoded) == 1
    if suffix == "jpg":
        assert converted == encoded
    with Image.open(output) as image:
        assert image.size == (785, 2400)
        assert image.info["icc_profile"] == PROFILE
