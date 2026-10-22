"""Exercise a built wheel from a clean installation outside the repository."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from browser_cli.browser.launch_preflight import ensure_browser_launch_allowed

NODE_SCENARIO = """
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {join} from 'node:path';
const [command, url] = process.argv.slice(2);
const {data: paths} = JSON.parse(execFileSync(command, ['paths', '--json'], {encoding:'utf8'}));
const {BrowserCliClient, DAEMON_RUNTIME_VERSION} = await import(pathToFileURL(paths.node_client).href);
// Leave socketPath unset to exercise installed path discovery and cold startup.
const client = new BrowserCliClient({command, home:paths.home});
try {
  const result = await client.batch([
    {action:'open', args:{url}},
    {action:'screenshot', args:{path:'wheel-smoke.png'}},
  ], {context:{viewport_width:640, viewport_height:480, device_scale_factor:2}, resultMode:'last'});
  assert.equal(result.data.success, true);
  assert.equal(result.data.context.closed, true);
  const shot = result.data.results[0].data;
  assert.deepEqual(shot.screenshot_size, {width:1280, height:960});
  assert.deepEqual(shot.capture.before, shot.capture.after);
  const failed = await client.batch([
    {action:'resize', args:{width:0, height:10}},
    {action:'open', args:{url}},
  ], {context:{}, resultMode:'summary'});
  assert.equal(failed.ok, true);
  assert.equal(failed.data.success, false);
  assert.equal(failed.data.completed_count, 1);
  assert.equal(failed.data.errors[0].error_code, 'INVALID_INPUT');
  assert.equal(failed.data.context.closed, true);
  const status = await client.status();
  assert.equal(status.data.runtime_version, DAEMON_RUNTIME_VERSION);
  assert.equal(status.data.profile_dir, join(paths.home, 'default-profile'));
  console.log(JSON.stringify({ok:true, node_client:paths.node_client, socket_path:client.socketPath,
    screenshot_size:shot.screenshot_size, failure_code:failed.data.errors[0].error_code,
    runtime_version:status.data.runtime_version, profile_dir:status.data.profile_dir}));
} finally {
  await client.request('stop', {}, {startIfNeeded:false});
}
"""


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"<!doctype html><html><body><h1>Installed wheel smoke test</h1></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def run(wheel: Path) -> dict[str, object]:
    ensure_browser_launch_allowed()
    node, uv = shutil.which("node"), shutil.which("uv")
    if node is None or uv is None:
        raise RuntimeError("uv and Node.js 18+ are required for the installed-wheel smoke test.")
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError(f"Wheel does not exist: {wheel}")
    with tempfile.TemporaryDirectory(prefix="bcli-wheel-") as temporary:
        root = Path(temporary).resolve()
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("VIRTUAL_ENV", None)
        env["BROWSER_CLI_HOME"] = str(root / "home")
        env["BROWSER_CLI_HEADLESS"] = "1"
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(root / "playwright")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            env["BROWSER_CLI_EXTENSION_PORT"] = str(probe.getsockname()[1])

        def execute(command: list[str], timeout: int = 120) -> str:
            result = subprocess.run(
                command, cwd=root, env=env, text=True, capture_output=True, timeout=timeout
            )
            if result.returncode:
                raise RuntimeError(
                    f"Command failed: {command[0]}\n{result.stdout}\n{result.stderr}"
                )
            return result.stdout

        venv = root / "venv"
        execute([uv, "venv", "--python", sys.executable, str(venv)])
        python = venv / "bin" / "python"
        execute([uv, "pip", "install", "--python", str(python), str(wheel)])
        # Managed Chrome records video, so a fresh install needs Playwright's
        # matching ffmpeg runtime even when Chrome is already installed.
        execute([str(python), "-m", "playwright", "install", "ffmpeg"])
        command = venv / "bin" / "browser-cli"
        paths = json.loads(execute([str(command), "paths", "--json"]))["data"]
        if not Path(paths["node_client"]).is_relative_to(venv):
            raise RuntimeError("Node client was resolved outside the clean installation.")
        scenario = root / "smoke.mjs"
        scenario.write_text(NODE_SCENARIO, encoding="utf-8")
        server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = json.loads(
                execute(
                    [node, str(scenario), str(command), f"http://127.0.0.1:{server.server_port}/"]
                )
            )
            return {"wheel": wheel.name, "clean_install": True, **result}
        finally:
            subprocess.run(
                [str(command), "stop"], cwd=root, env=env, capture_output=True, timeout=20
            )
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.wheel.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
