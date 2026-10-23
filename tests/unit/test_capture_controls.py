from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, patch

import pytest

from browser_cli.browser.capture import PAGE_GEOMETRY_JS, CaptureOptions, image_dimensions
from browser_cli.browser.context import ContextOptions
from browser_cli.browser.raster import PAINTABLE_VIEWPORT_JS
from browser_cli.browser.service import BrowserService
from browser_cli.errors import InvalidInputError, OperationFailedError

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg=="
)


class CapturePage:
    def __init__(self, *, fail=False):
        self.viewport_size = {"width": 1440, "height": 1024}
        self.position = {"x": 0, "y": 300}
        self.viewport_changes = []
        self.cdp = AsyncMock()
        self.cdp.send.return_value = {"data": base64.b64encode(PNG).decode()}

        async def send(method, params):
            if fail and method == "Page.captureScreenshot":
                raise RuntimeError("capture failed")
            return {"data": base64.b64encode(PNG).decode()}

        self.cdp.send.side_effect = send
        self.context = AsyncMock()
        self.context.new_cdp_session.return_value = self.cdp

    async def evaluate(self, script, arg=None):
        if script == PAINTABLE_VIEWPORT_JS:
            return dict(self.viewport_size)
        if script == PAGE_GEOMETRY_JS:
            return {
                "viewport_width": self.viewport_size["width"],
                "viewport_height": self.viewport_size["height"],
                "page_width": self.viewport_size["width"],
                "page_height": 2400,
                "scroll_x": self.position["x"],
                "scroll_y": self.position["y"],
                "device_scale_factor": 1,
            }
        if arg is not None:
            self.position = arg
        return True

    async def set_viewport_size(self, size):
        self.viewport_changes.append(size)
        self.viewport_size = size
        self.position = {"x": 0, "y": 0}


def test_full_page_capture_uses_a_rectangle_without_resizing(tmp_path):
    page = CapturePage()
    service = BrowserService()
    service._pages["page_1"] = page
    with patch(
        "browser_cli.browser.service.capture_tiled", new_callable=AsyncMock, return_value=PNG
    ) as capture:
        result = asyncio.run(
            service.screenshot(
                "page_1", path=str(tmp_path / "full.png"), full_page=True, device_scale_factor=2
            )
        )
    assert page.viewport_changes == []
    capture.assert_awaited_once()
    assert capture.await_args.args[2] == {"x": 0, "y": 0, "width": 1440, "height": 2400, "scale": 2}
    assert capture.await_args.kwargs["density"] == 2
    assert all(call.args[0] != "Page.captureScreenshot" for call in page.cdp.send.call_args_list)
    assert result["screenshot_size"] == {"width": 1, "height": 1}
    assert result["capture"]["before"] == result["capture"]["after"]
    page.cdp.detach.assert_not_awaited()


@pytest.mark.parametrize("fail", [False, True])
def test_temporary_viewport_and_scroll_are_restored_even_after_capture_failure(tmp_path, fail):
    page = CapturePage(fail=fail)
    service = BrowserService()
    service._pages["page_1"] = page
    output = tmp_path / "viewport.png"

    async def scenario():
        return await service.screenshot(
            "page_1", path=str(output), viewport_width=800, viewport_height=600
        )

    if fail:
        with pytest.raises(RuntimeError, match="capture failed"):
            asyncio.run(scenario())
        assert not output.exists()
    else:
        result = asyncio.run(scenario())
        assert result["capture"]["viewport"] == {"width": 800, "height": 600}
        assert result["capture"]["page_dimensions_unchanged"] is True
    assert page.viewport_size == {"width": 1440, "height": 1024}
    assert page.position == {"x": 0, "y": 300}
    page.cdp.detach.assert_not_awaited()


@pytest.mark.parametrize(
    "args",
    [
        {"clip": {"x": -1, "y": 0, "width": 10, "height": 10}},
        {"clip": {"x": 0, "y": 0, "width": 0, "height": 10}},
        {"clip": {"x": 0, "y": 0, "width": 10, "height": 10}, "full_page": True},
        {"viewport_width": 800},
        {"viewport_width": True, "viewport_height": 600},
        {"device_scale_factor": float("nan")},
        {"device_scale_factor": 0},
        {"full_page": "false"},
    ],
)
def test_capture_rejects_invalid_controls(args):
    with pytest.raises(InvalidInputError):
        CaptureOptions.from_dict(args)


def test_image_dimensions_rejects_non_images():
    with pytest.raises(OperationFailedError):
        image_dimensions(b"not an image")


@pytest.mark.parametrize(
    "args",
    [
        {"locale": "bad_locale"},
        {"timezone_id": "Invalid/Zone"},
        {"unknown": 1},
        {"zoom": float("inf")},
        {"viewport_width": None, "viewport_height": None},
        {"device_scale_factor": None},
        {"font_files": [{"family": "Demo", "path": "/no/such/font.woff2"}]},
    ],
)
def test_context_rejects_unreproducible_settings(args):
    with pytest.raises(InvalidInputError):
        ContextOptions.from_dict(args)


def test_context_font_bytes_are_embedded_in_each_document(tmp_path):
    font = tmp_path / "fixture.ttf"
    font.write_bytes(b"test font")
    options = ContextOptions.from_dict(
        {
            "font_files": [{"family": "Fixture", "path": str(font)}],
            "font_family": "Fixture",
            "zoom": 1.25,
        }
    )
    script = options.init_script()
    assert "data:font/ttf;base64,dGVzdCBmb250" in script
    assert "zoom: 1.25 !important" in script
    assert options.metadata()["zoom_method"] == "css"


@pytest.mark.parametrize("restores", [True, False])
def test_capture_waits_for_scrollbar_restoration_without_accepting_persistent_changes(
    tmp_path, restores
):
    class ScrollbarPage(CapturePage):
        def __init__(self):
            super().__init__()
            self.captured = False
            self.after_reads = 0
            send = self.cdp.send.side_effect

            async def screenshot_send(method, params):
                if method == "Page.captureScreenshot":
                    self.captured = True
                return await send(method, params)

            self.cdp.send.side_effect = screenshot_send

        async def evaluate(self, script, arg=None):
            result = await super().evaluate(script, arg)
            if script == PAGE_GEOMETRY_JS:
                if self.captured:
                    self.after_reads += 1
                # Renderer geometry updates may lag metric restoration.
                result["page_width"] = (
                    1440 if self.captured and (not restores or self.after_reads < 3) else 1425
                )
            return result

    page = ScrollbarPage()
    service = BrowserService()
    service._pages["scrollbar"] = page
    output = tmp_path / "scrollbar.png"
    if restores:
        result = asyncio.run(service.screenshot("scrollbar", path=str(output)))
        assert result["capture"]["before"] == result["capture"]["after"]
        assert result["capture"]["after"]["page_width"] == 1425
        assert page.after_reads >= 3
        assert output.is_file()
    else:
        with pytest.raises(OperationFailedError, match="Page geometry changed"):
            asyncio.run(service.screenshot("scrollbar", path=str(output)))
        assert not output.exists()
