from __future__ import annotations

import asyncio
import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from browser_cli.cli.main import main
from browser_cli.daemon.client import send_command
from browser_cli.errors import AmbiguousRefError, BusyTabError, NoSnapshotContextError, StaleSnapshotError
from browser_cli.profiles.discovery import discover_chrome_executable
from tests.integration.fixture_server import run_fixture_server


def _can_launch_daemon_browser() -> bool:
    try:
        executable_path = discover_chrome_executable()
    except Exception:
        return False

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False

    async def _probe() -> bool:
        playwright = await async_playwright().start()
        with tempfile.TemporaryDirectory() as tmp:
            user_data_dir = Path(tmp) / "user-data"
            user_data_dir.mkdir(parents=True)
            try:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    executable_path=str(executable_path),
                    headless=True,
                )
                await context.close()
                return True
            except Exception:
                return False
            finally:
                await playwright.stop()

    return asyncio.run(_probe())


pytestmark = pytest.mark.integration


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _configure_runtime(
    monkeypatch,
    tmp_path: Path,
    *,
    agent_id: str = "agent-a",
    search_url_template: str | None = None,
) -> None:
    real_home = Path.home()
    if not (real_home / "Library" / "Caches" / "ms-playwright").exists() and sys.platform.startswith("linux"):
        playwright_cache = real_home / ".cache" / "ms-playwright"
    else:
        playwright_cache = real_home / "Library" / "Caches" / "ms-playwright"
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(playwright_cache))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BROWSER_CLI_HOME", str(tmp_path / ".browser-cli-runtime"))
    monkeypatch.setenv("X_AGENT_ID", agent_id)
    monkeypatch.setenv("BROWSER_CLI_HEADLESS", "1")
    monkeypatch.setenv("BROWSER_CLI_EXTENSION_PORT", str(_unused_port()))
    if search_url_template:
        monkeypatch.setenv("BROWSER_CLI_SEARCH_URL_TEMPLATE", search_url_template)


def _run_cli_json(args: list[str], capsys) -> dict:
    exit_code = main(args)
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    return json.loads(captured.out)


def _run_cli_text(args: list[str], capsys) -> str:
    exit_code = main(args)
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    return captured.out


def _stop_daemon(capsys) -> None:
    main(["stop"])
    capsys.readouterr()


def _find_ref(refs_summary: list[dict], *, role: str, name: str) -> str:
    for item in refs_summary:
        if item.get("role") == role and item.get("name") == name:
            return str(item["ref"])
    raise AssertionError(f"Missing ref for role={role!r} name={name!r}")


def _snapshot_refs(capsys) -> list[dict]:
    return _run_cli_json(["snapshot"], capsys)["data"]["refs_summary"]


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_status_and_reload_lifecycle_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    with run_fixture_server() as base_url:
        _configure_runtime(monkeypatch, tmp_path)

        initial_status = _run_cli_text(["status"], capsys)
        assert "Status: stopped" in initial_status

        reload_status = _run_cli_text(["reload"], capsys)
        assert "Reload: complete" in reload_status
        assert "result: healthy" in reload_status

        current_status = _run_cli_text(["status"], capsys)
        assert "Status: healthy" in current_status
        assert "profile source: -" in current_status

        open_payload = _run_cli_json(["open", f"{base_url}/static"], capsys)
        assert open_payload["data"]["page"]["url"].endswith("/static")

        _stop_daemon(capsys)


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_navigation_and_lifecycle_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    with run_fixture_server() as base_url:
        _configure_runtime(
            monkeypatch,
            tmp_path,
            search_url_template=f"{base_url}/search?engine={{engine}}&q={{query}}",
        )

        open_payload = _run_cli_json(["open", f"{base_url}/interactive"], capsys)
        first_page_id = open_payload["data"]["page"]["page_id"]
        refs_summary = _snapshot_refs(capsys)
        nav_link_ref = _find_ref(refs_summary, role="link", name="Navigate To Nav Two")

        _run_cli_json(["click", nav_link_ref], capsys)
        wait_nav = _run_cli_json(["wait", "5", "--text", "Nav Two"], capsys)
        assert wait_nav["data"]["state"] == "visible"

        back_payload = _run_cli_json(["back"], capsys)
        assert back_payload["data"]["page"]["url"].endswith("/interactive")

        forward_payload = _run_cli_json(["forward"], capsys)
        assert forward_payload["data"]["page"]["url"].endswith("/nav-two")

        reload_payload = _run_cli_json(["page-reload"], capsys)
        assert reload_payload["data"]["page"]["title"] == "Nav Two"

        resize_payload = _run_cli_json(["resize", "1200", "820"], capsys)
        assert resize_payload["data"]["width"] == 1200
        assert resize_payload["data"]["height"] == 820

        info_payload = _run_cli_json(["info"], capsys)
        assert info_payload["data"]["page"]["viewport_width"] == 1200
        assert info_payload["data"]["page"]["viewport_height"] == 820

        new_tab_payload = _run_cli_json(["new-tab", f"{base_url}/static"], capsys)
        second_page_id = new_tab_payload["data"]["page"]["page_id"]
        assert second_page_id != first_page_id

        tabs_payload = _run_cli_json(["tabs"], capsys)
        assert [tab["page_id"] for tab in tabs_payload["data"]["tabs"]] == [second_page_id, first_page_id]

        switch_payload = _run_cli_json(["switch-tab", first_page_id], capsys)
        assert switch_payload["data"]["page"]["page_id"] == first_page_id

        search_payload = _run_cli_json(["search", "browser cli", "--engine", "bing"], capsys)
        search_page_id = search_payload["data"]["page"]["page_id"]
        assert search_payload["data"]["page"]["url"].startswith(f"{base_url}/search")

        verify_url = _run_cli_json(["verify-url", "/search?engine=bing"], capsys)
        assert verify_url["data"]["passed"] is True

        verify_title = _run_cli_json(["verify-title", "Search Fixture"], capsys)
        assert verify_title["data"]["passed"] is True

        close_active = _run_cli_json(["close"], capsys)
        assert close_active["data"]["page_id"] == search_page_id

        close_second = _run_cli_json(["close-tab", second_page_id], capsys)
        assert close_second["data"]["page_id"] == second_page_id

        _stop_daemon(capsys)


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_snapshot_html_and_element_interaction_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    with run_fixture_server() as base_url:
        _configure_runtime(monkeypatch, tmp_path)
        _run_cli_json(["open", f"{base_url}/interactive"], capsys)

        snapshot_payload = _run_cli_json(["snapshot"], capsys)
        refs_summary = snapshot_payload["data"]["refs_summary"]
        assert "Interactive Fixture" in snapshot_payload["data"]["tree"]

        html_payload = _run_cli_json(["html"], capsys)
        assert "Interactive Fixture" in html_payload["data"]["html"]
        assert "data-browser-cli-ref" not in html_payload["data"]["html"]

        reveal_ref = _find_ref(refs_summary, role="button", name="Reveal Message")
        hide_ref = _find_ref(refs_summary, role="button", name="Hide Message")
        name_ref = _find_ref(refs_summary, role="textbox", name="Name Input")
        email_ref = _find_ref(refs_summary, role="textbox", name="Email Input")
        select_ref = _find_ref(refs_summary, role="combobox", name="Color Select")
        checkbox_ref = _find_ref(refs_summary, role="checkbox", name="Agree Checkbox")
        radio_ref = _find_ref(refs_summary, role="radio", name="Blue Radio")
        focus_ref = _find_ref(refs_summary, role="textbox", name="Focus Input")
        double_click_ref = _find_ref(refs_summary, role="button", name="Double Click Button")
        hover_ref = _find_ref(refs_summary, role="button", name="Hover Target")
        upload_ref = _find_ref(refs_summary, role="button", name="Upload File")
        drag_source_ref = _find_ref(refs_summary, role="button", name="Drag Source")
        drag_target_ref = _find_ref(refs_summary, role="button", name="Drop Target")
        deep_target_ref = _find_ref(refs_summary, role="button", name="Deep Target")
        disabled_button_ref = _find_ref(refs_summary, role="button", name="Disabled Button")

        fill_submit = _run_cli_json(["fill", name_ref, "Alice", "--submit"], capsys)
        assert fill_submit["data"]["submitted"] is True
        _run_cli_json(["wait", "5", "--text", "submitted:Alice:"], capsys)

        fill_form = _run_cli_json(
            [
                "fill-form",
                "--fields",
                json.dumps(
                    [
                        {"ref": name_ref, "text": "Bob"},
                        {"ref": email_ref, "text": "bob@example.com"},
                    ]
                ),
                "--submit",
            ],
            capsys,
        )
        assert fill_form["data"]["filled_fields"] == 2
        _run_cli_json(["wait", "5", "--text", "submitted:Bob:bob@example.com"], capsys)

        options_payload = _run_cli_json(["options", select_ref], capsys)
        assert options_payload["data"]["options"] == ["Red", "Blue", "Green"]

        select_payload = _run_cli_json(["select", select_ref, "Blue"], capsys)
        assert select_payload["data"]["selected"] == "Blue"

        _run_cli_json(["check", checkbox_ref], capsys)
        _run_cli_json(["check", radio_ref], capsys)
        checked_payload = _run_cli_json(["verify-state", checkbox_ref, "checked"], capsys)
        assert checked_payload["data"]["passed"] is True

        _run_cli_json(["uncheck", checkbox_ref], capsys)
        unchecked_payload = _run_cli_json(["verify-state", checkbox_ref, "unchecked"], capsys)
        assert unchecked_payload["data"]["passed"] is True

        focus_payload = _run_cli_json(["focus", focus_ref], capsys)
        assert focus_payload["data"]["action"] == "focus"

        hover_payload = _run_cli_json(["hover", hover_ref], capsys)
        assert hover_payload["data"]["action"] == "hover"

        double_click_payload = _run_cli_json(["double-click", double_click_ref], capsys)
        assert double_click_payload["data"]["action"] == "double-click"
        dbl_status = _run_cli_json(["eval", "() => document.getElementById('dbl-status').textContent"], capsys)
        assert dbl_status["data"]["result"] == "1"

        click_payload = _run_cli_json(["click", reveal_ref], capsys)
        assert click_payload["data"]["action"] == "click"
        _run_cli_json(["wait", "5", "--text", "Revealed"], capsys)
        _run_cli_json(["click", hide_ref], capsys)
        wait_gone = _run_cli_json(["wait", "5", "--text", "Revealed", "--gone"], capsys)
        assert wait_gone["data"]["state"] == "hidden"

        upload_file = tmp_path / "upload.txt"
        upload_file.write_text("upload payload", encoding="utf-8")
        upload_payload = _run_cli_json(["upload", upload_ref, str(upload_file)], capsys)
        assert upload_payload["data"]["file_path"].endswith("upload.txt")
        upload_status = _run_cli_json(["eval", "() => document.getElementById('upload-status').textContent"], capsys)
        assert upload_status["data"]["result"] == "upload.txt"

        drag_payload = _run_cli_json(["drag", drag_source_ref, drag_target_ref], capsys)
        assert drag_payload["data"]["dragged"] is True
        drag_status = _run_cli_json(["eval", "() => document.getElementById('drag-status').textContent"], capsys)
        assert drag_status["data"]["result"] == "drag-source"

        scroll_to_payload = _run_cli_json(["scroll-to", deep_target_ref], capsys)
        assert scroll_to_payload["data"]["scrolled"] is True
        scroll_y = _run_cli_json(["eval", "() => window.scrollY"], capsys)
        assert scroll_y["data"]["result"] > 0

        verify_text = _run_cli_json(["verify-text", "Interactive Fixture"], capsys)
        assert verify_text["data"]["passed"] is True

        verify_visible = _run_cli_json(["verify-visible", "button", "Reveal Message"], capsys)
        assert verify_visible["data"]["passed"] is True

        verify_disabled = _run_cli_json(["verify-state", disabled_button_ref, "disabled"], capsys)
        assert verify_disabled["data"]["passed"] is True

        verify_editable = _run_cli_json(["verify-state", name_ref, "editable"], capsys)
        assert verify_editable["data"]["passed"] is True

        verify_value = _run_cli_json(["verify-value", name_ref, "Bob"], capsys)
        assert verify_value["data"]["passed"] is True

        _stop_daemon(capsys)


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_semantic_ref_recovers_after_rerender_and_iframe(monkeypatch, tmp_path: Path, capsys) -> None:
    with run_fixture_server() as base_url:
        _configure_runtime(monkeypatch, tmp_path)

        _run_cli_json(["open", f"{base_url}/semantic"], capsys)
        semantic_refs = _snapshot_refs(capsys)
        target_ref = _find_ref(semantic_refs, role="button", name="Semantic Target")
        rerender_ref = _find_ref(semantic_refs, role="button", name="Rerender Stable Target")

        _run_cli_json(["click", target_ref], capsys)
        first_status = _run_cli_json(["eval", "() => document.getElementById('semantic-status').textContent"], capsys)
        assert first_status["data"]["result"] == "1"

        _run_cli_json(["click", rerender_ref], capsys)
        _run_cli_json(["click", target_ref], capsys)
        second_status = _run_cli_json(["eval", "() => document.getElementById('semantic-status').textContent"], capsys)
        assert second_status["data"]["result"] == "2"

        _run_cli_json(["open", f"{base_url}/iframe"], capsys)
        iframe_refs = _snapshot_refs(capsys)
        frame_ref = _find_ref(iframe_refs, role="button", name="Frame Trigger")
        _run_cli_json(["click", frame_ref], capsys)
        frame_status = _run_cli_json(["eval", "() => document.getElementById('frame-status').textContent"], capsys)
        assert frame_status["data"]["result"] == "clicked"

        _stop_daemon(capsys)


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_semantic_ref_errors_are_explicit(monkeypatch, tmp_path: Path, capsys) -> None:
    with run_fixture_server() as base_url:
        _configure_runtime(monkeypatch, tmp_path)
        _run_cli_json(["open", f"{base_url}/semantic"], capsys)

        with pytest.raises(NoSnapshotContextError):
            send_command("click", {"ref": "aaaaaaaa"})

        semantic_refs = _snapshot_refs(capsys)
        target_ref = _find_ref(semantic_refs, role="button", name="Semantic Target")
        duplicate_ref = _find_ref(semantic_refs, role="button", name="Duplicate Semantic Target")
        rename_ref = _find_ref(semantic_refs, role="button", name="Rename Semantic Target")

        _run_cli_json(["click", duplicate_ref], capsys)
        with pytest.raises(AmbiguousRefError):
            send_command("click", {"ref": target_ref})

        _run_cli_json(["page-reload"], capsys)
        semantic_refs = _snapshot_refs(capsys)
        target_ref = _find_ref(semantic_refs, role="button", name="Semantic Target")
        rename_ref = _find_ref(semantic_refs, role="button", name="Rename Semantic Target")
        _run_cli_json(["click", rename_ref], capsys)
        with pytest.raises(StaleSnapshotError):
            send_command("click", {"ref": target_ref})

        _stop_daemon(capsys)


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_keyboard_mouse_wait_and_eval_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    with run_fixture_server() as base_url:
        _configure_runtime(monkeypatch, tmp_path)
        _run_cli_json(["open", f"{base_url}/interactive"], capsys)

        refs_summary = _snapshot_refs(capsys)
        focus_ref = _find_ref(refs_summary, role="textbox", name="Focus Input")
        reveal_ref = _find_ref(refs_summary, role="button", name="Reveal Message")

        _run_cli_json(["focus", focus_ref], capsys)

        type_payload = _run_cli_json(["type", "Hello"], capsys)
        assert type_payload["data"]["typed"] is True
        typed_value = _run_cli_json(["eval-on", focus_ref, "(el) => el.value"], capsys)
        assert typed_value["data"]["result"] == "Hello"

        press_payload = _run_cli_json(["press", "Enter"], capsys)
        assert press_payload["data"]["key"] == "Enter"
        key_status = _run_cli_json(["eval", "() => document.getElementById('key-status').textContent"], capsys)
        assert key_status["data"]["result"] == "up:Enter"

        _run_cli_json(["key-down", "Shift"], capsys)
        key_down_status = _run_cli_json(["eval", "() => document.getElementById('key-status').textContent"], capsys)
        assert key_down_status["data"]["result"] == "down:Shift"

        _run_cli_json(["key-up", "Shift"], capsys)
        key_up_status = _run_cli_json(["eval", "() => document.getElementById('key-status').textContent"], capsys)
        assert key_up_status["data"]["result"] == "up:Shift"

        rect_payload = _run_cli_json(
            [
                "eval",
                "() => { const r = document.getElementById('mouse-pad').getBoundingClientRect(); return { x: Math.round(r.left + 20), y: Math.round(r.top + 20), x2: Math.round(r.left + 120), y2: Math.round(r.top + 60) }; }",
            ],
            capsys,
        )
        coords = rect_payload["data"]["result"]

        _run_cli_json(["mouse-move", str(coords["x"]), str(coords["y"])], capsys)
        _run_cli_json(["mouse-down"], capsys)
        down_status = _run_cli_json(["eval", "() => document.getElementById('mouse-status').textContent"], capsys)
        assert down_status["data"]["result"].startswith("mousedown:")

        _run_cli_json(["mouse-up"], capsys)
        up_status = _run_cli_json(["eval", "() => document.getElementById('mouse-status').textContent"], capsys)
        assert up_status["data"]["result"].startswith(("mouseup:", "click:"))

        _run_cli_json(["mouse-click", str(coords["x2"]), str(coords["y2"])], capsys)
        click_status = _run_cli_json(["eval", "() => document.getElementById('mouse-status').textContent"], capsys)
        assert click_status["data"]["result"].startswith("click:")

        _run_cli_json(
            ["mouse-drag", str(coords["x"]), str(coords["y"]), str(coords["x2"]), str(coords["y2"])],
            capsys,
        )
        drag_status = _run_cli_json(["eval", "() => document.getElementById('mouse-status').textContent"], capsys)
        assert drag_status["data"]["result"].startswith(("mousemove:", "mouseup:", "click:"))

        scroll_payload = _run_cli_json(["scroll", "--dy", "900"], capsys)
        assert scroll_payload["data"]["dy"] == 900
        info_payload = _run_cli_json(["info"], capsys)
        assert info_payload["data"]["page"]["scroll_y"] > 0

        wait_seconds = _run_cli_json(["wait", "0.05"], capsys)
        assert wait_seconds["data"]["seconds"] == 0.05

        _run_cli_json(["click", reveal_ref], capsys)
        wait_text = _run_cli_json(["wait", "5", "--text", "Revealed"], capsys)
        assert wait_text["data"]["state"] == "visible"

        eval_payload = _run_cli_json(["eval", "() => document.title"], capsys)
        assert eval_payload["data"]["result"] == "Interactive Fixture"

        _stop_daemon(capsys)


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_capture_network_dialog_storage_trace_and_video_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    with run_fixture_server() as base_url:
        _configure_runtime(monkeypatch, tmp_path)
        open_payload = _run_cli_json(["open", f"{base_url}/interactive"], capsys)
        page_id = open_payload["data"]["page"]["page_id"]
        refs_summary = _snapshot_refs(capsys)

        fetch_ref = _find_ref(refs_summary, role="button", name="Fetch Data")
        load_static_ref = _find_ref(refs_summary, role="button", name="Load Static Assets")
        console_ref = _find_ref(refs_summary, role="button", name="Console Error")
        alert_ref = _find_ref(refs_summary, role="button", name="Alert Button")
        confirm_ref = _find_ref(refs_summary, role="button", name="Confirm Button")
        prompt_ref = _find_ref(refs_summary, role="button", name="Prompt Button")
        storage_ref = _find_ref(refs_summary, role="button", name="Storage Button")

        _run_cli_json(["console-start"], capsys)
        _run_cli_json(["click", fetch_ref], capsys)
        waited_record = _run_cli_json(["network-wait", "--url-contains", "/api/ping?from=button", "--timeout", "5"], capsys)
        assert waited_record["data"]["record"]["status"] == 200
        assert waited_record["data"]["record"]["body"]["kind"] == "text"
        assert waited_record["data"]["record"]["body"]["text"] == '{"ok":true}'

        _run_cli_json(["network-start"], capsys)
        _run_cli_json(["click", fetch_ref], capsys)
        _run_cli_json(["wait-network"], capsys)
        _run_cli_json(["click", load_static_ref], capsys)
        _run_cli_json(["wait-network"], capsys)
        _run_cli_json(["click", console_ref], capsys)

        network_payload = _run_cli_json(["network", "--no-clear"], capsys)
        urls = [record["url"] for record in network_payload["data"]["records"]]
        assert any("/api/ping?from=button" in url for url in urls)
        assert not any("/asset.js" in url for url in urls)
        api_records = [record for record in network_payload["data"]["records"] if "/api/ping?from=button" in record["url"]]
        assert any(record["response_headers"]["content-type"].startswith("application/json") for record in api_records)

        network_static_payload = _run_cli_json(["network", "--include-static"], capsys)
        static_urls = [record["url"] for record in network_static_payload["data"]["records"]]
        assert any("/asset.js" in url for url in static_urls)
        assert any("/styles.css" in url for url in static_urls)

        console_payload = _run_cli_json(["console", "--type", "error", "--no-clear"], capsys)
        assert any(message["text"] == "fixture-error" for message in console_payload["data"]["messages"])
        console_stopped = _run_cli_json(["console-stop"], capsys)
        assert console_stopped["data"]["capturing"] is False
        network_stopped = _run_cli_json(["network-stop"], capsys)
        assert network_stopped["data"]["capturing"] is False

        screenshot_path = tmp_path / "shot.png"
        pdf_path = tmp_path / "page.pdf"
        screenshot_payload = _run_cli_json(["screenshot", str(screenshot_path), "--full-page"], capsys)
        assert Path(screenshot_payload["data"]["path"]).exists()
        pdf_payload = _run_cli_json(["pdf", str(pdf_path)], capsys)
        assert Path(pdf_payload["data"]["path"]).exists()

        _run_cli_json(["dialog-setup", "--action", "accept", "--text", "auto-prompt"], capsys)
        _run_cli_json(["click", prompt_ref], capsys)
        _run_cli_json(["wait", "5", "--text", "prompt:auto-prompt"], capsys)
        dialog_removed = _run_cli_json(["dialog-remove"], capsys)
        assert dialog_removed["data"]["removed"] is True

        _run_cli_json(["dialog", "--dismiss"], capsys)
        _run_cli_json(["click", confirm_ref], capsys)
        _run_cli_json(["wait", "5", "--text", "confirm:false"], capsys)

        _run_cli_json(["dialog"], capsys)
        _run_cli_json(["click", alert_ref], capsys)
        _run_cli_json(["wait", "5", "--text", "alert:done"], capsys)

        _run_cli_json(["click", storage_ref], capsys)
        storage_status = _run_cli_json(["eval", "() => document.getElementById('storage-status').textContent"], capsys)
        assert storage_status["data"]["result"] == "stored-token"

        _run_cli_json(["cookie-set", "theme", "dark"], capsys)
        cookies_payload = _run_cli_json(["cookies", "--name", "theme"], capsys)
        assert any(cookie["name"] == "theme" for cookie in cookies_payload["data"]["cookies"])

        state_path = tmp_path / "storage-state.json"
        storage_save = _run_cli_json(["storage-save", str(state_path)], capsys)
        assert Path(storage_save["data"]["path"]).exists()

        _run_cli_json(["cookies-clear", "--name", "theme"], capsys)
        cleared_cookies = _run_cli_json(["cookies", "--name", "theme"], capsys)
        assert cleared_cookies["data"]["cookies"] == []

        cleared_storage = _run_cli_json(
            ["eval", "() => { localStorage.clear(); return localStorage.getItem('fixture-token'); }"],
            capsys,
        )
        assert cleared_storage["data"]["result"] is None

        storage_load = _run_cli_json(["storage-load", str(state_path)], capsys)
        assert storage_load["data"]["cookies_loaded"] >= 1

        loaded_cookie = _run_cli_json(["cookies", "--name", "theme"], capsys)
        assert any(cookie["name"] == "theme" for cookie in loaded_cookie["data"]["cookies"])

        loaded_storage = _run_cli_json(["eval", "() => localStorage.getItem('fixture-token')"], capsys)
        assert loaded_storage["data"]["result"] == "stored-token"

        trace_path = tmp_path / "trace.zip"
        _run_cli_json(["trace-start"], capsys)
        trace_chunk = _run_cli_json(["trace-chunk", "after-open"], capsys)
        assert trace_chunk["data"]["chunk_started"] is True
        _run_cli_json(["click", fetch_ref], capsys)
        trace_stop = _run_cli_json(["trace-stop", str(trace_path)], capsys)
        assert Path(trace_stop["data"]["path"]).exists()
        assert Path(trace_stop["data"]["path"]).stat().st_size > 0

        _run_cli_json(["video-start", "--width", "800", "--height", "600"], capsys)
        _run_cli_json(["click", fetch_ref], capsys)
        planned_video = _run_cli_json(["video-stop", str(tmp_path / "demo-video")], capsys)
        assert planned_video["data"]["deferred"] is True

        close_payload = _run_cli_json(["close-tab", page_id], capsys)
        video_path = Path(close_payload["data"]["video_path"])
        assert video_path.exists()
        assert video_path.suffix == ".webm"

        _stop_daemon(capsys)


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_agent_visibility_isolation(monkeypatch, tmp_path: Path, capsys) -> None:
    with run_fixture_server() as base_url:
        _configure_runtime(monkeypatch, tmp_path, agent_id="agent-a")
        _run_cli_json(["open", f"{base_url}/static"], capsys)

        monkeypatch.setenv("X_AGENT_ID", "agent-b")
        _run_cli_json(["open", f"{base_url}/dynamic"], capsys)

        tabs_b = _run_cli_json(["tabs"], capsys)
        assert len(tabs_b["data"]["tabs"]) == 1
        assert "/dynamic" in tabs_b["data"]["tabs"][0]["url"]

        monkeypatch.setenv("X_AGENT_ID", "agent-a")
        tabs_a = _run_cli_json(["tabs"], capsys)
        assert len(tabs_a["data"]["tabs"]) == 1
        assert "/static" in tabs_a["data"]["tabs"][0]["url"]

        _stop_daemon(capsys)


@pytest.mark.skipif(not _can_launch_daemon_browser(), reason="Stable Chrome runtime unavailable")
def test_busy_active_tab_returns_explicit_error(monkeypatch, tmp_path: Path, capsys) -> None:
    _configure_runtime(monkeypatch, tmp_path, agent_id="agent-a")
    with run_fixture_server() as base_url:
        _run_cli_json(["open", f"{base_url}/interactive"], capsys)

        result_box: dict[str, object] = {}

        def _run_long_eval() -> None:
            result_box["payload"] = send_command(
                "eval",
                {
                    "code": "async () => { await new Promise((resolve) => setTimeout(resolve, 700)); return 'done'; }",
                },
            )

        thread = threading.Thread(target=_run_long_eval)
        thread.start()
        time.sleep(0.15)
        with pytest.raises(BusyTabError):
            send_command("html")
        thread.join(timeout=5)
        assert result_box["payload"]["ok"] is True

        _stop_daemon(capsys)
