"""Capture and isolation contracts share one Chrome launch, with host preflight first."""

from __future__ import annotations

import asyncio
import json
import shutil
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from tests.integration.fixture_server import run_fixture_server

from browser_cli.browser.context import ContextOptions
from browser_cli.browser.launch_preflight import ensure_browser_launch_allowed
from browser_cli.constants import get_app_paths
from browser_cli.daemon.app import BrowserDaemonApp
from browser_cli.daemon.models import DaemonRequest
from browser_cli.daemon.server import BrowserDaemonServer
from browser_cli.daemon.transport import DAEMON_RUNTIME_VERSION
from browser_cli.profiles.discovery import ChromeEnvironment, discover_chrome_executable

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def browser_runtime(tmp_path_factory):
    # Check the real host restriction before any Playwright process can be started.
    # Permission denial is a setup error, never a passing availability probe.
    ensure_browser_launch_allowed()
    root = tmp_path_factory.mktemp("capture-context")
    loop = asyncio.new_event_loop()
    with pytest.MonkeyPatch.context() as env, run_fixture_server() as url:
        env.setenv("BROWSER_CLI_HOME", str(root / "runtime"))
        env.setenv("BROWSER_CLI_HEADLESS", "1")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            env.setenv("BROWSER_CLI_EXTENSION_PORT", str(probe.getsockname()[1]))
        app = BrowserDaemonApp()
        app.state.browser_service.configure_environment(
            ChromeEnvironment(
                executable_path=discover_chrome_executable(),
                user_data_dir=root / "profile",
                profile_directory="Default",
                source="managed",
            )
        )
        try:
            loop.run_until_complete(app.state.browser_service.ensure_started())
            yield SimpleNamespace(
                loop=loop,
                app=app,
                url=url,
                root=root,
                socket=get_app_paths().socket_path,
                low=app.state.browser_service._playwright._service,
            )
        finally:
            loop.run_until_complete(app.state.browser_service.stop())
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()


@pytest.fixture
def runtime(browser_runtime):
    # The shared test cleanup removes runtime sockets after each test; the
    # listener is per test while the browser process remains shared by the module.
    transport = BrowserDaemonServer(browser_runtime.app)

    async def listen():
        browser_runtime.socket.parent.mkdir(parents=True, exist_ok=True)
        return await asyncio.start_unix_server(
            transport._handle_client, path=str(browser_runtime.socket)
        )

    server = browser_runtime.loop.run_until_complete(listen())
    try:
        yield browser_runtime
    finally:
        server.close()
        browser_runtime.loop.run_until_complete(server.wait_closed())
        browser_runtime.socket.unlink(missing_ok=True)


async def command(runtime, action, **args):
    response = await runtime.app.execute(DaemonRequest(action, args, "capture-test", "request"))
    assert response.ok, response.to_dict()
    return response.data


def test_real_screenshot_dimensions_ranges_dpr_and_restoration(runtime):
    async def scenario():
        await command(runtime, "open", url=runtime.url + "/static")
        await command(runtime, "resize", width=800, height=600)
        await command(
            runtime,
            "eval",
            code="() => { document.body.style.height = '2400px'; scrollTo(0, 300); }",
        )
        for name, options in [
            ("full.png", {"full_page": True}),
            ("clip.png", {"clip": {"x": 100, "y": 300, "width": 123, "height": 77}}),
            ("viewport.png", {"viewport_width": 640, "viewport_height": 480}),
            ("viewport.jpg", {"viewport_width": 640, "viewport_height": 480}),
        ]:
            data = await command(
                runtime,
                "screenshot",
                path=str(runtime.root / name),
                device_scale_factor=2,
                **options,
            )
            capture = data["capture"]
            assert capture["before"] == capture["after"]
            assert capture["before"]["viewport_width"] == 800
            assert capture["before"]["scroll_y"] == 300
            assert capture["page_dimensions_unchanged"] is True
            assert data["screenshot_size"] == {
                "width": round(capture["clip"]["width"] * 2),
                "height": round(capture["clip"]["height"] * 2),
            }
            assert Path(data["path"]).is_file()

    runtime.loop.run_until_complete(scenario())


def test_context_is_repeatable_isolated_and_closed_after_success_and_error(runtime):
    async def scenario():
        await command(runtime, "open", url=runtime.url + "/static")
        await command(
            runtime,
            "eval",
            code="() => { localStorage.setItem('shared', 'parent'); document.cookie = 'shared=parent'; }",
        )
        browser = runtime.low._context.browser
        baseline_count = len(browser.contexts)
        context = {
            "viewport_width": 640,
            "viewport_height": 480,
            "device_scale_factor": 2,
            "zoom": 1.25,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "font_family": "Arial",
        }
        settings = []
        images = []
        for index in range(2):
            result = await command(
                runtime,
                "batch",
                context=context,
                commands=[
                    {"action": "open", "args": {"url": runtime.url + "/static"}},
                    {
                        "action": "eval",
                        "args": {
                            "code": """() => ({ language: navigator.language,
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    dpr: devicePixelRatio, width: innerWidth, height: innerHeight,
                    zoom: getComputedStyle(document.documentElement).zoom,
                    font: getComputedStyle(document.body).fontFamily,
                    shared: localStorage.getItem('shared'), cookies: document.cookie })"""
                        },
                    },
                    {
                        "action": "screenshot",
                        "args": {"path": str(runtime.root / f"context-{index}.png")},
                    },
                    {
                        "action": "eval",
                        "args": {
                            "code": "() => { localStorage.setItem('shared', 'child'); document.cookie = 'shared=child'; }"
                        },
                    },
                ],
            )
            assert result["success"] is True, json.dumps(result)
            assert result["context"]["closed"] is True
            settings.append(result["results"][1]["data"]["result"])
            shot = result["results"][2]["data"]
            assert shot["screenshot_size"] == {"width": 1280, "height": 960}
            images.append(Path(shot["path"]).read_bytes())
            assert len(browser.contexts) == baseline_count
        assert (
            settings[0]
            == settings[1]
            == {
                "language": "zh-CN",
                "timezone": "Asia/Shanghai",
                "dpr": 2,
                "width": 640,
                "height": 480,
                "zoom": "1.25",
                "font": "Arial",
                "shared": None,
                "cookies": "",
            }
        )
        assert images[0] == images[1]
        shared = await command(runtime, "eval", code="() => localStorage.getItem('shared')")
        assert shared["result"] == "parent"
        failed = await command(
            runtime,
            "batch",
            context={},
            commands=[
                {"action": "resize", "args": {"width": 500, "height": 500}},
                {"action": "open", "args": {"url": runtime.url + "/static"}},
            ],
        )
        assert failed["success"] is False
        assert failed["completed_count"] == 1
        assert failed["context"]["closed"] is True
        assert len(browser.contexts) == baseline_count

    runtime.loop.run_until_complete(scenario())


def test_node_client_runs_an_isolated_batch_over_the_real_daemon_transport(runtime):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    module = Path(__file__).resolve().parents[2] / "src/browser_cli/task_runtime/node/client.mjs"
    script = f"""import {{ BrowserCliClient }} from {json.dumps(module.as_uri())};
        const client = new BrowserCliClient({{ socketPath: {json.dumps(str(runtime.socket))}, agentId: 'node-integration' }});
        const result = await client.batch([
          {{action:'open',args:{{url:{json.dumps(runtime.url + "/static")}}}}},
          {{action:'eval',args:{{code:'() => ({{width: innerWidth, language: navigator.language}})'}}}}
        ], {{context:{{viewport_width:900,viewport_height:700,locale:'en-GB'}}, resultMode:'last',startIfNeeded:false}});
        console.log(JSON.stringify(result));
    """

    async def scenario():
        process = await asyncio.create_subprocess_exec(
            node,
            "--input-type=module",
            "-e",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        assert process.returncode == 0, stderr.decode()
        result = json.loads(stdout)
        assert result["ok"] is True
        assert result["data"]["success"] is True
        assert result["data"]["context"]["closed"] is True
        assert result["data"]["results"][0]["data"]["result"] == {"width": 900, "language": "en-GB"}

    runtime.loop.run_until_complete(scenario())


def test_context_applies_fonts_and_zoom_on_pages_with_strict_csp(runtime):
    async def scenario():
        isolated = await runtime.low.create_isolated_service(
            ContextOptions.from_dict({"zoom": 1.5, "font_family": "测试字体"})
        )
        try:

            async def fulfill(route):
                await route.fulfill(
                    status=200,
                    headers={
                        "content-type": "text/html",
                        "content-security-policy": "default-src 'none'; style-src 'none'; font-src 'none'",
                    },
                    body="<!doctype html><html><body>Controlled fonts</body></html>",
                )

            await isolated._context.route("**/csp", fulfill)
            await isolated.new_tab(page_id="csp", url=runtime.url + "/csp")
            result = await isolated.evaluate(
                "csp",
                "() => ({zoom: getComputedStyle(document.documentElement).zoom, font: getComputedStyle(document.body).fontFamily})",
            )
            assert result["result"]["zoom"] == "1.5"
            assert result["result"]["font"].strip('"') == "测试字体"
        finally:
            await isolated.stop()

    runtime.loop.run_until_complete(scenario())


@pytest.mark.parametrize("continue_on_error", [False, True])
def test_canceling_a_running_batch_closes_real_context_and_releases_browser(
    runtime, continue_on_error
):
    async def scenario():
        await command(runtime, "open", url=runtime.url + "/static")
        browser = runtime.low._context.browser
        baseline = len(browser.contexts)
        entered = asyncio.Event()
        create_context = runtime.low.create_isolated_service

        async def create_observed_context(options):
            service = await create_context(options)
            await service._context.expose_binding("batchEntered", lambda source: entered.set())
            return service

        observer = patch.object(
            runtime.low, "create_isolated_service", side_effect=create_observed_context
        )
        observer.start()
        task = asyncio.create_task(
            runtime.app.execute(
                DaemonRequest(
                    "batch",
                    {
                        "context": {},
                        "stop_on_error": not continue_on_error,
                        "commands": [
                            {"action": "open", "args": {"url": runtime.url + "/static"}},
                            {
                                "action": "eval",
                                "args": {
                                    "code": "() => { window.batchEntered(); return new Promise(() => {}); }"
                                },
                            },
                            {
                                "action": "screenshot",
                                "args": {
                                    "path": str(runtime.root / f"canceled-{continue_on_error}.png")
                                },
                            },
                        ],
                    },
                    "cancel-test",
                    "cancel-request",
                )
            )
        )

        try:
            await asyncio.wait_for(entered.wait(), 10)
        finally:
            task.cancel()
            try:
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                observer.stop()
        assert len(browser.contexts) == baseline
        assert not (runtime.root / f"canceled-{continue_on_error}.png").exists()
        assert runtime.app.state.browser_service._command_depth == 0
        result = await asyncio.wait_for(command(runtime, "eval", code="() => 42"), 5)
        assert result["result"] == 42

    runtime.loop.run_until_complete(scenario())


@pytest.mark.parametrize("disconnect", [False, True])
def test_disconnected_or_timed_out_client_does_not_replay_and_eventually_closes_context(
    runtime, disconnect
):
    async def scenario():
        browser = runtime.low._context.browser
        baseline = len(browser.contexts)
        output = runtime.root / f"after-disconnect-{disconnect}.png"
        commands = [
            {"action": "open", "args": {"url": runtime.url + "/static"}},
            {
                "action": "eval",
                "args": {
                    "code": "() => new Promise(resolve => setTimeout(() => resolve(42), 700))"
                },
            },
            {"action": "screenshot", "args": {"path": str(output)}},
        ]
        if disconnect:
            reader, writer = await asyncio.open_unix_connection(str(runtime.socket))
            writer.write(
                (
                    json.dumps(
                        {
                            "action": "batch",
                            "args": {"context": {}, "commands": commands},
                            "agent_id": "disconnected-client",
                            "request_id": "disconnect",
                            "runtime_version": DAEMON_RUNTIME_VERSION,
                        }
                    )
                    + "\n"
                ).encode()
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        else:
            node = shutil.which("node")
            assert node, "Node.js is required for the client timeout contract"
            module = (
                Path(__file__).resolve().parents[2] / "src/browser_cli/task_runtime/node/client.mjs"
            )
            script = f"""import {{BrowserCliClient}} from {json.dumps(module.as_uri())};
                const client = new BrowserCliClient({{socketPath: {json.dumps(str(runtime.socket))}, timeoutMs: 250}});
                try {{ await client.batch({json.dumps(commands)}, {{context:{{}}, startIfNeeded:false}}); process.exitCode=1; }}
                catch (error) {{ console.log(JSON.stringify({{code:error.code}})); }}"""
            process = await asyncio.create_subprocess_exec(
                node,
                "--input-type=module",
                "-e",
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), 10)
            assert process.returncode == 0, stderr.decode()
            assert json.loads(stdout)["code"] == "CLIENT_TIMEOUT"

        async def wait_for_completion():
            while not output.exists() or len(browser.contexts) != baseline:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_for_completion(), 10)
        assert runtime.app.state.browser_service._command_depth == 0
        status = await command(runtime, "runtime-status", warmup=False)
        assert status["runtime_version"] == DAEMON_RUNTIME_VERSION

    with patch.object(
        runtime.low, "create_isolated_service", wraps=runtime.low.create_isolated_service
    ) as create_context:
        runtime.loop.run_until_complete(scenario())
        create_context.assert_awaited_once()


@pytest.mark.parametrize("custom_scrollbar", [False, True])
def test_repeated_captures_restore_native_and_classic_scrollbar_layout(runtime, custom_scrollbar):
    async def scenario():
        await command(runtime, "open", url=runtime.url + "/static")
        await command(runtime, "resize", width=800, height=600)
        page_id = await runtime.app.state.tabs.current_active_page_id("capture-test")
        page = runtime.low._pages[page_id]
        scrollbar_css = "::-webkit-scrollbar { width: 15px; }" if custom_scrollbar else ""
        await page.set_content(
            "<!doctype html><style>html { overflow-y: scroll; }"
            "body { margin: 0; height: 2400px; }" + scrollbar_css + "</style>"
            '<div style="width:100%;height:100px;background:red">Scrollbar capture</div>'
        )
        await page.evaluate("() => scrollTo(0, 300)")
        before = await page.evaluate(
            "() => ({width: document.documentElement.clientWidth, scroll: scrollY})"
        )
        if custom_scrollbar:
            assert before["width"] == 785
        for index in range(3):
            result = await command(
                runtime,
                "screenshot",
                full_page=True,
                path=str(runtime.root / f"scrollbar-{custom_scrollbar}-{index}.png"),
            )
            assert result["capture"]["before"] == result["capture"]["after"]
            assert (
                await page.evaluate(
                    "() => ({width: document.documentElement.clientWidth, scroll: scrollY})"
                )
                == before
            )

    runtime.loop.run_until_complete(scenario())
