"""Replay fixed local workflows over the real daemon socket; no model is invoked.

Run with ``uv run python -m scripts.benchmark_agent_workflows --output PATH``.
The same workloads can be replayed before and after a source change. Browser
startup, simulated sign-in, and cleanup are outside each measured task. All
task requests and their complete UTF-8 response envelopes are counted.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import socket
import statistics
import tempfile
import time
from collections import Counter
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from tests.agent_workflow_fixture import PAGES, workflow_server
from tests.browser_runtime import get_test_browser_executable

from browser_cli.browser.launch_preflight import ensure_browser_launch_allowed
from browser_cli.constants import get_app_paths
from browser_cli.daemon.app import BrowserDaemonApp
from browser_cli.daemon.models import DaemonRequest
from browser_cli.daemon.server import BrowserDaemonServer
from browser_cli.profiles.discovery import ChromeEnvironment

TASKS = ("account", "form", "pagination", "recovery", "timeout", "cancel", "disconnect")


@asynccontextmanager
async def local_runtime():
    # Never probe launch availability by trying to start Chrome.
    ensure_browser_launch_allowed()
    executable = get_test_browser_executable()
    with tempfile.TemporaryDirectory(prefix="bcli-workflows-") as directory:
        root = Path(directory)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with (
            patch.dict(
                os.environ,
                {
                    "BROWSER_CLI_HOME": str(root),
                    "BROWSER_CLI_HEADLESS": "1",
                    "BROWSER_CLI_LOCALE": "en-US",
                    "TZ": "UTC",
                    "BROWSER_CLI_EXTENSION_PORT": str(port),
                },
            ),
            workflow_server() as url,
        ):
            app = BrowserDaemonApp()
            app.state.browser_service.configure_environment(
                ChromeEnvironment(
                    executable_path=executable,
                    user_data_dir=root / "profile",
                    profile_directory="Default",
                    source="managed",
                )
            )
            transport = BrowserDaemonServer(app)
            get_app_paths().socket_path.parent.mkdir(parents=True, exist_ok=True)
            server = await asyncio.start_unix_server(
                transport._handle_client,
                path=str(get_app_paths().socket_path),
            )
            try:
                await app.state.browser_service.ensure_started()
                # Deliberately simulated, HttpOnly login state; never return cookie data.
                runner = Replay(app, url)
                await runner.request("open", url=url + "/seed")
                await runner.request("close")
                yield app, url, executable
            finally:
                server.close()
                await server.wait_closed()
                await app.state.browser_service.stop()


class Replay:
    def __init__(self, app, url, *, compact=False, composed=False, focus_main=False):
        self.app, self.url = app, url
        self.compact, self.composed = compact, composed
        self.focus_main = focus_main
        self.responses = []
        self.errors = Counter()
        self.browser_ms = 0.0
        self.driver_ms = 0.0
        self.driver_calls = 0
        self.browser_actions = 0
        self.response_bytes = 0
        self.request_count = 0

    async def request(self, action, **args):
        self.request_count += 1
        reader, writer = await asyncio.open_unix_connection(
            str(get_app_paths().socket_path),
            limit=32 * 1024 * 1024,
        )
        payload = {
            "action": action,
            "args": args,
            "agent_id": "workflow-bench",
            "request_id": f"replay-{self.request_count}",
        }
        try:
            writer.write((json.dumps(payload) + "\n").encode())
            await writer.drain()
            raw = await reader.readline()
        finally:
            writer.close()
            await writer.wait_closed()
        self.response_bytes += len(raw)
        response = json.loads(raw)
        self.responses.append(response)
        if not response["ok"]:
            self.errors[response["error_code"]] += 1
        elif action == "batch":
            for error in response["data"]["errors"]:
                self.errors[error["error_code"]] += 1
        return response

    async def data(self, action, **args):
        result = await self.request(action, **args)
        assert result["ok"], result
        return result["data"]

    async def snapshot(self):
        args = {"compact": True} if self.compact else {}
        if self.focus_main:
            args["roles"] = ["main"]
        return await self.data("snapshot", **args)

    async def group(self, commands):
        if self.composed:
            result = await self.data("batch", commands=commands, result_mode="last")
            assert result["success"], result
            return result["results"][-1]["data"]
        result = {}
        for command in commands:
            result = await self.data(command["action"], **command.get("args", {}))
        return result

    @staticmethod
    def ref(snapshot, role, name):
        matches = [
            item["ref"]
            for item in snapshot["refs_summary"]
            if item["role"] == role and item.get("name") == name
        ]
        assert len(matches) == 1, (role, name, matches)
        return matches[0]

    async def account(self):
        await self.data("open", url=self.url + "/account")
        snapshot = await self.snapshot()
        assert "fixture-user" in snapshot["tree"]
        result = (
            await self.data(
                "eval",
                code="""() => ({
          account: document.querySelector('#account').textContent,
          plan: document.querySelector('#plan').textContent,
          credits: Number(document.querySelector('#credits').textContent)
        })""",
            )
        )["result"]
        assert result == {"account": "fixture-user", "plan": "Research", "credits": 42}
        return result

    async def form(self):
        await self.data("open", url=self.url + "/form")
        snapshot = await self.snapshot()
        result = await self.group(
            [
                {
                    "action": "fill",
                    "args": {"ref": self.ref(snapshot, "textbox", "Name"), "text": "Local User"},
                },
                {
                    "action": "select",
                    "args": {"ref": self.ref(snapshot, "combobox", "Region"), "text": "North"},
                },
                {"action": "wait", "args": {"text": "North ready", "seconds": 2}},
                {"action": "click", "args": {"ref": self.ref(snapshot, "button", "Preview draft")}},
                {
                    "action": "eval",
                    "args": {"code": "() => document.querySelector('#result').textContent"},
                },
            ]
        )
        assert result["result"] == "Local User / North", result
        return result["result"]

    async def pagination(self):
        await self.data("open", url=self.url + "/list")
        snapshot = await self.snapshot()
        next_ref = self.ref(snapshot, "button", "Next page")
        result = []
        for page in range(1, 4):
            if page > 1:
                await self.group(
                    [
                        {"action": "click", "args": {"ref": next_ref}},
                        {
                            "action": "wait",
                            "args": {"text": f"Page {page}", "seconds": 2, "exact": True},
                        },
                    ]
                )
            value = (
                await self.data(
                    "eval",
                    code="""() => ({
              items: Array.from(document.querySelectorAll('tbody tr'), row => ({
                name: row.cells[0].textContent, price: Number(row.cells[1].textContent)
              })), done: document.querySelector('#next').disabled
            })""",
                )
            )["result"]
            result.extend(value["items"])
            if value["done"]:
                break
        assert result == [{"name": f"Item {i}", "price": i * 3} for i in range(1, 13)]
        return result

    async def recovery(self):
        await self.data("open", url=self.url + "/resilience")
        snapshot = await self.snapshot()
        await self.group(
            [
                {"action": "click", "args": {"ref": self.ref(snapshot, "button", "Reveal later")}},
                {"action": "wait", "args": {"text": "Delayed action", "seconds": 2}},
            ]
        )
        # Preserve the old snapshot so changing the label genuinely invalidates its locator.
        await self.data("click", ref=self.ref(snapshot, "button", "Replace target"))
        stale = await self.request("click", ref=self.ref(snapshot, "button", "Original action"))
        assert stale["error_code"] == "STALE_SNAPSHOT", stale
        refreshed = await self.snapshot()
        assert self.ref(refreshed, "button", "Changed action")
        await self.data("click", ref=self.ref(refreshed, "link", "Account page"))
        await self.data("wait", text="Test account", seconds=2)
        final = await self.snapshot()
        assert "fixture-user" in final["tree"]
        return {"delayed": True, "stale_detected": True, "navigated": True}

    async def timeout(self):
        await self.data("open", url=self.url + "/resilience")
        response = await self.request(
            "batch",
            commands=[
                {
                    "action": "eval",
                    "args": {
                        "code": "() => document.querySelector('#marker').textContent = 'once'"
                    },
                },
                {"action": "wait", "args": {"text": "Never appears", "seconds": 0.15}},
                {
                    "action": "eval",
                    "args": {
                        "code": "() => document.querySelector('#marker').textContent = 'wrong'"
                    },
                },
            ],
        )
        data = response["data"]
        assert response["ok"] and not data["success"] and data["completed_count"] == 2, response
        marker = (
            await self.data("eval", code="() => document.querySelector('#marker').textContent")
        )["result"]
        assert marker == "once"
        return {"stopped": True, "earlier_effect_retained": True}

    async def interruption(self, *, disconnect):
        await self.data("open", url=self.url + "/resilience")
        entered, finished = asyncio.Event(), asyncio.Event()
        original_wait = self.app._handlers["wait"]
        original_execute = self.app.execute

        async def wait_step(request):
            entered.set()
            return await original_wait(request)

        async def execute(request):
            try:
                return await original_execute(request)
            finally:
                if request.request_id == "interruption-batch":
                    finished.set()

        commands = [
            {
                "action": "eval",
                "args": {"code": "() => document.querySelector('#marker').dataset.effects = '1'"},
            },
            {"action": "wait", "args": {"seconds": 0.3}},
            {
                "action": "eval",
                "args": {"code": "() => ++document.querySelector('#marker').dataset.effects"},
            },
        ]
        with (
            patch.dict(self.app._handlers, {"wait": wait_step}),
            patch.object(self.app, "execute", execute),
        ):
            reader, writer = await asyncio.open_unix_connection(str(get_app_paths().socket_path))
            self.request_count += 1
            writer.write(
                (
                    json.dumps(
                        {
                            "action": "batch",
                            "args": {"commands": commands},
                            "agent_id": "workflow-bench",
                            "request_id": "interruption-batch",
                        }
                    )
                    + "\n"
                ).encode()
            )
            await writer.drain()
            try:
                await asyncio.wait_for(entered.wait(), 3)
                if disconnect:
                    writer.close()
                    await writer.wait_closed()
                    await asyncio.wait_for(finished.wait(), 3)
                else:
                    closed = await self.data("close")
                    assert closed["closed"] is True, closed
                    raw = await asyncio.wait_for(reader.readline(), 3)
                    self.response_bytes += len(raw)
                    interrupted = json.loads(raw)
                    assert interrupted["execution_state"] == "unknown", interrupted
                    self.errors[interrupted["error_code"]] += 1
                    await asyncio.wait_for(finished.wait(), 3)
            finally:
                writer.close()
                await writer.wait_closed()
        if disconnect:
            effects = (
                await self.data(
                    "eval", code="() => Number(document.querySelector('#marker').dataset.effects)"
                )
            )["result"]
            assert effects == 2, effects
            return {"continued_after_disconnect": True, "effects": effects, "replayed": False}
        return {"closed": True, "result_unknown": True}

    async def cancel(self):
        return await self.interruption(disconnect=False)

    async def disconnect(self):
        return await self.interruption(disconnect=True)

    async def run(self, task):
        original = self.app._execute

        async def measured(request):
            if request.action == "batch":
                return await original(request)
            started = time.perf_counter()
            try:
                return await original(request)
            finally:
                self.browser_ms += (time.perf_counter() - started) * 1000
                self.browser_actions += 1

        def instrument(method):
            async def timed(*args, **kwargs):
                before = time.perf_counter()
                try:
                    return await method(*args, **kwargs)
                finally:
                    self.driver_ms += (time.perf_counter() - before) * 1000
                    self.driver_calls += 1

            return timed

        started = time.perf_counter()
        passed, failure, result = False, None, None
        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(self.app, "_execute", measured))
                driver = self.app.state.browser_service._active_driver()
                for name in (
                    "new_tab",
                    "get_page_summary",
                    "capture_snapshot_input",
                    "evaluate",
                    "fill",
                    "select_option",
                    "wait",
                    "click",
                    "close_tab",
                ):
                    stack.enter_context(
                        patch.object(driver, name, instrument(getattr(driver, name)))
                    )
                result = await getattr(self, task)()
            passed = True
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
        elapsed = (time.perf_counter() - started) * 1000
        # Each replay represents one ordinary host script. This is not an Agent
        # run and therefore does not measure actual Agent tools, model turns or tokens.
        record = {
            "task": task,
            "passed": passed,
            "failure": failure,
            "total_ms": elapsed,
            "browser_action_ms": self.browser_ms,
            "browser_driver_ms": self.driver_ms,
            "browser_driver_calls": self.driver_calls,
            "daemon_requests": self.request_count,
            "browser_actions": self.browser_actions,
            "response_bytes": self.response_bytes,
            "final_result_bytes": len(json.dumps(result).encode()),
            "errors": dict(self.errors),
            "retries": 0,
            "host_script_invocations": 1,
            "agent_tool_calls": None,
            "model_rounds": None,
            "model_tokens": None,
            "model_ms": None,
        }
        for tab in await self.app.state.tabs.list_tabs("workflow-bench"):
            await self.app.execute(
                DaemonRequest("close-tab", {"page_id": tab.page_id}, "workflow-bench", "cleanup")
            )
        return record


async def benchmark(args):
    async with local_runtime() as (app, url, executable):
        rows = []
        for sample in range(args.samples + args.warmups):
            # Alternate strategy order to reduce drift from caches and host load.
            modes = [False, True] if sample % 2 == 0 else [True, False]
            for composed in modes:
                for task in TASKS:
                    replay = Replay(
                        app,
                        url,
                        compact=args.compact,
                        composed=composed,
                        focus_main=args.focus_main,
                    )
                    row = await replay.run(task)
                    if sample >= args.warmups:
                        rows.append(
                            {
                                **row,
                                "sample": sample - args.warmups,
                                "strategy": "composed" if composed else "individual",
                            }
                        )
        summaries = []
        for strategy in ("individual", "composed"):
            for task in TASKS:
                selected = [
                    row for row in rows if row["strategy"] == strategy and row["task"] == task
                ]
                summary = {
                    "strategy": strategy,
                    "task": task,
                    "n": len(selected),
                    "passed": sum(row["passed"] for row in selected),
                }
                for key in (
                    "total_ms",
                    "browser_action_ms",
                    "browser_driver_ms",
                    "browser_driver_calls",
                    "daemon_requests",
                    "browser_actions",
                    "response_bytes",
                    "final_result_bytes",
                    "retries",
                ):
                    summary[key + "_median"] = statistics.median(row[key] for row in selected)
                summary["errors"] = dict(
                    sum((Counter(row["errors"]) for row in selected), Counter())
                )
                summaries.append(summary)
        return {
            "schema_version": 1,
            "compact": args.compact,
            "focus_main": args.focus_main,
            "samples": args.samples,
            "warmups": args.warmups,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "executable": str(executable),
            "fixture_sha256": hashlib.sha256(
                json.dumps(PAGES, sort_keys=True).encode()
            ).hexdigest(),
            "measurement": {
                "browser_action_ms": "daemon dispatch wall time excluding batch wrappers; includes browser waits and bookkeeping",
                "browser_driver_ms": "sum of timed driver calls (including waits and summaries); overlapping cancellation spans may exceed task wall time",
                "response_bytes": "complete newline-terminated daemon response envelopes, UTF-8",
                "agent_tools_and_model_metrics": "unmeasured; deterministic client replay, not a real Agent",
                "startup_login_cleanup": "outside measured task",
            },
            "summaries": summaries,
            "runs": rows,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument(
        "--focus-main",
        action="store_true",
        help="Keep the fixture's main task region using the role view.",
    )
    args = parser.parse_args()
    if args.samples < 1 or args.warmups < 0:
        parser.error("samples must be positive and warmups nonnegative")
    result = asyncio.run(benchmark(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for summary in result["summaries"]:
        print(json.dumps(summary))
    raise SystemExit(0 if all(row["passed"] for row in result["runs"]) else 1)


if __name__ == "__main__":
    main()
