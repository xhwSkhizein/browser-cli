from __future__ import annotations

from browser_cli.browser.stealth import (
    build_context_options,
    build_ignore_default_args,
    build_init_script,
    build_launch_args,
)


def test_build_launch_args_headed_uses_minimal_profile():
    args = build_launch_args(
        headless=False,
        viewport_width=1440,
        viewport_height=900,
        locale="zh-CN",
    )
    assert "--headless=new" not in args
    assert "--disable-background-networking" not in args
    assert "--disable-infobars" in args
    assert "--lang=zh-CN" in args
    assert "--window-size=1440,900" in args
    disable_features = next(arg for arg in args if arg.startswith("--disable-features="))
    assert "AutomationControlled" in disable_features
    assert "InfiniteSessionRestore" in disable_features


def test_build_launch_args_headless_uses_extended_profile():
    args = build_launch_args(
        headless=True,
        viewport_width=1600,
        viewport_height=1024,
        locale="en-US",
    )
    assert "--headless=new" in args
    assert "--disable-background-networking" in args
    assert "--hide-scrollbars" in args
    assert "--mute-audio" in args
    assert "--window-size=1600,1024" in args


def test_build_ignore_default_args_includes_automation_and_scrollbars():
    args = build_ignore_default_args()
    assert "--enable-automation" in args
    assert "--hide-scrollbars" in args


def test_build_context_options_aligns_locale_and_screen():
    options = build_context_options(
        viewport_width=1440,
        viewport_height=1024,
        locale="zh_CN.UTF-8",
    )
    assert options["locale"] == "zh-CN"
    assert options["screen"] == {"width": 1440, "height": 1024}
    assert options["accept_downloads"] is True
    assert "notifications" in options["permissions"]


def test_build_init_script_skips_headed_injection():
    assert build_init_script(headless=False, locale="zh-CN") is None


def test_build_init_script_headless_contains_extended_patches():
    script = build_init_script(headless=True, locale="zh-CN")
    assert script is not None
    assert '"zh-CN"' in script
    assert "navigator, 'plugins'" in script
    assert "Notification.permission" in script
    assert "hardwareConcurrency" in script
    assert "WebGLRenderingContext" in script
