from __future__ import annotations

import contextlib
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


STATIC_PAGE = """<!doctype html>
<html>
  <head><title>Static Fixture</title></head>
  <body><main><h1>Static Fixture</h1><p>Static content.</p></main></body>
</html>
"""

DYNAMIC_PAGE = """<!doctype html>
<html>
  <head><title>Dynamic Fixture</title></head>
  <body>
    <main id="app"><p>Loading...</p></main>
    <script>
      setTimeout(() => {
        document.querySelector('#app').innerHTML = '<h1>Dynamic Fixture</h1><p>Rendered content.</p>';
      }, 150);
    </script>
  </body>
</html>
"""

LAZY_PAGE = """<!doctype html>
<html>
  <head><title>Lazy Fixture</title></head>
  <body>
    <main id="feed">
      <article>Lazy Item 1</article>
      <article>Lazy Item 2</article>
    </main>
    <script>
      let loads = 0;
      const ensureSpace = () => {
        document.body.style.minHeight = (2200 + loads * 900) + 'px';
      };
      const appendMore = () => {
        if (loads >= 2) return;
        loads += 1;
        const item = document.createElement('article');
        item.textContent = 'Lazy Item ' + (loads + 2);
        document.querySelector('#feed').appendChild(item);
        ensureSpace();
      };
      ensureSpace();
      window.addEventListener('scroll', () => {
        if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 5) {
          setTimeout(appendMore, 120);
        }
      });
    </script>
  </body>
</html>
"""

INTERACTIVE_PAGE = """<!doctype html>
<html>
  <head>
    <title>Interactive Fixture</title>
    <link rel="stylesheet" href="/styles.css">
    <script src="/asset.js"></script>
    <style>
      body { font-family: sans-serif; }
      main { max-width: 960px; margin: 0 auto; padding: 24px; }
      section { margin-bottom: 24px; padding: 16px; border: 1px solid #d0d7de; border-radius: 8px; }
      #hover-target, #drag-source, #drag-target, #mouse-pad {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border: 1px solid #57606a;
        border-radius: 8px;
        background: #f6f8fa;
      }
      #hover-target, #drag-source, #drag-target { width: 160px; height: 64px; margin-right: 12px; }
      #mouse-pad { width: 240px; height: 120px; user-select: none; }
      .spacer { height: 1800px; }
    </style>
  </head>
  <body>
    <main>
      <h1>Interactive Fixture</h1>

      <section>
        <a id="nav-link" href="/nav-two">Navigate To Nav Two</a>
        <button id="reveal" aria-label="Reveal Message">Reveal Message</button>
        <button id="hide" aria-label="Hide Message">Hide Message</button>
        <p id="message">Waiting</p>
      </section>

      <section>
        <form id="user-form">
          <label for="name">Name</label>
          <input id="name" aria-label="Name Input" type="text" placeholder="Name">
          <label for="email">Email</label>
          <input id="email" aria-label="Email Input" type="email" placeholder="Email">
          <button type="submit" aria-label="Submit Form">Submit Form</button>
        </form>
        <p id="form-status">idle</p>

        <label for="focus-input">Focus</label>
        <input id="focus-input" aria-label="Focus Input" type="text">
        <p id="focus-status">blurred</p>
        <p id="key-status">idle</p>

        <label for="color">Color</label>
        <select id="color" aria-label="Color Select">
          <option value="red">Red</option>
          <option value="blue">Blue</option>
          <option value="green">Green</option>
        </select>
        <p id="select-status">red</p>

        <label><input id="agree" aria-label="Agree Checkbox" type="checkbox"> Agree</label>
        <label><input id="radio-blue" aria-label="Blue Radio" type="radio" name="choice" value="blue"> Blue</label>
        <p id="check-status">unchecked</p>
        <button id="disabled-button" aria-label="Disabled Button" disabled>Disabled Button</button>
      </section>

      <section>
        <button id="dbl" aria-label="Double Click Button">Double Click Button</button>
        <p id="dbl-status">0</p>
        <div id="hover-target" role="button" tabindex="0" aria-label="Hover Target">Hover Target</div>
        <p id="hover-status">idle</p>
      </section>

      <section>
        <input id="upload-input" aria-label="Upload File" type="file">
        <p id="upload-status">none</p>
        <div id="drag-source" draggable="true" role="button" tabindex="0" aria-label="Drag Source">Drag Source</div>
        <div id="drag-target" role="button" tabindex="0" aria-label="Drop Target">Drop Target</div>
        <p id="drag-status">pending</p>
      </section>

      <section>
        <div id="mouse-pad" aria-label="Mouse Pad"></div>
        <p id="mouse-status">idle</p>
        <button id="fetch-button" aria-label="Fetch Data">Fetch Data</button>
        <button id="load-static-button" aria-label="Load Static Assets">Load Static Assets</button>
        <button id="console-button" aria-label="Console Error">Console Error</button>
      </section>

      <section>
        <button id="alert-button" aria-label="Alert Button">Alert</button>
        <button id="confirm-button" aria-label="Confirm Button">Confirm</button>
        <button id="prompt-button" aria-label="Prompt Button">Prompt</button>
        <p id="dialog-status">none</p>
      </section>

      <section>
        <button id="storage-button" aria-label="Storage Button">Storage Button</button>
        <p id="storage-status">empty</p>
      </section>

      <div class="spacer"></div>
      <button id="deep-target" aria-label="Deep Target">Deep Target</button>
    </main>

    <script>
      const setText = (id, value) => {
        document.getElementById(id).textContent = String(value);
      };

      document.getElementById('reveal').addEventListener('click', async () => {
        console.log('reveal-clicked');
        await fetch('/api/ping?from=reveal');
        setText('message', 'Revealed');
      });

      document.getElementById('hide').addEventListener('click', () => {
        setText('message', 'Waiting');
      });

      document.getElementById('user-form').addEventListener('submit', (event) => {
        event.preventDefault();
        const name = document.getElementById('name').value;
        const email = document.getElementById('email').value;
        setText('form-status', `submitted:${name}:${email}`);
      });

      document.getElementById('focus-input').addEventListener('focus', () => setText('focus-status', 'focused'));
      document.getElementById('focus-input').addEventListener('blur', () => setText('focus-status', 'blurred'));
      document.getElementById('focus-input').addEventListener('keydown', (event) => setText('key-status', `down:${event.key}`));
      document.getElementById('focus-input').addEventListener('keyup', (event) => setText('key-status', `up:${event.key}`));

      document.getElementById('color').addEventListener('change', (event) => {
        setText('select-status', event.target.value);
      });

      document.getElementById('agree').addEventListener('change', (event) => {
        setText('check-status', event.target.checked ? 'checked' : 'unchecked');
      });

      document.getElementById('radio-blue').addEventListener('change', (event) => {
        if (event.target.checked) {
          setText('check-status', 'radio:blue');
        }
      });

      document.getElementById('dbl').addEventListener('dblclick', () => {
        const current = Number(document.getElementById('dbl-status').textContent || '0');
        setText('dbl-status', current + 1);
      });

      document.getElementById('hover-target').addEventListener('mouseenter', () => {
        setText('hover-status', 'hovered');
      });

      document.getElementById('upload-input').addEventListener('change', (event) => {
        const file = event.target.files && event.target.files[0];
        setText('upload-status', file ? file.name : 'none');
      });

      document.getElementById('drag-source').addEventListener('dragstart', (event) => {
        event.dataTransfer.setData('text/plain', 'drag-source');
      });
      document.getElementById('drag-target').addEventListener('dragover', (event) => {
        event.preventDefault();
      });
      document.getElementById('drag-target').addEventListener('drop', (event) => {
        event.preventDefault();
        setText('drag-status', event.dataTransfer.getData('text/plain'));
      });

      const mousePad = document.getElementById('mouse-pad');
      const updateMouse = (label, event) => {
        const x = Math.round(event.clientX);
        const y = Math.round(event.clientY);
        setText('mouse-status', `${label}:${x},${y}`);
      };
      ['mousemove', 'mousedown', 'mouseup', 'click'].forEach((name) => {
        document.addEventListener(name, (event) => updateMouse(name, event), true);
      });

      document.getElementById('fetch-button').addEventListener('click', async () => {
        await fetch('/api/ping?from=button');
      });

      document.getElementById('load-static-button').addEventListener('click', () => {
        const stamp = Date.now();
        const script = document.createElement('script');
        script.src = `/asset.js?stamp=${stamp}`;
        document.body.appendChild(script);
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = `/styles.css?stamp=${stamp}`;
        document.head.appendChild(link);
      });

      document.getElementById('console-button').addEventListener('click', () => {
        console.error('fixture-error');
      });

      document.getElementById('alert-button').addEventListener('click', () => {
        alert('fixture-alert');
        setText('dialog-status', 'alert:done');
      });

      document.getElementById('confirm-button').addEventListener('click', () => {
        const result = confirm('fixture-confirm');
        setText('dialog-status', `confirm:${result}`);
      });

      document.getElementById('prompt-button').addEventListener('click', () => {
        const value = prompt('fixture-prompt', 'default');
        setText('dialog-status', `prompt:${value === null ? 'null' : value}`);
      });

      document.getElementById('storage-button').addEventListener('click', () => {
        localStorage.setItem('fixture-token', 'stored-token');
        setText('storage-status', localStorage.getItem('fixture-token'));
      });
    </script>
  </body>
</html>
"""

NAV_TWO_PAGE = """<!doctype html>
<html>
  <head><title>Nav Two</title></head>
  <body><main><h1>Nav Two</h1><p>Second page.</p></main></body>
</html>
"""


def _build_search_page(query: str, engine: str) -> str:
    return f"""<!doctype html>
<html>
  <head><title>Search Fixture</title></head>
  <body>
    <main>
      <h1>Search Fixture</h1>
      <p id="engine">{engine}</p>
      <p id="query">{query}</p>
    </main>
  </body>
</html>
"""


ASSET_JS = "console.log('fixture-asset-loaded');"
STYLES_CSS = "body { background: #fff; }"


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/static":
            self._send_html(STATIC_PAGE)
            return
        if parsed.path == "/dynamic":
            self._send_html(DYNAMIC_PAGE)
            return
        if parsed.path == "/lazy":
            self._send_html(LAZY_PAGE)
            return
        if parsed.path == "/interactive":
            self._send_html(INTERACTIVE_PAGE)
            return
        if parsed.path == "/nav-two":
            self._send_html(NAV_TWO_PAGE)
            return
        if parsed.path == "/search":
            self._send_html(
                _build_search_page(
                    query.get("q", [""])[0],
                    query.get("engine", ["duckduckgo"])[0],
                )
            )
            return
        if parsed.path == "/asset.js":
            self._send_bytes(ASSET_JS.encode("utf-8"), "application/javascript; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._send_bytes(STYLES_CSS.encode("utf-8"), "text/css; charset=utf-8")
            return
        if parsed.path == "/api/ping":
            self._send_bytes(b'{"ok":true}', "application/json")
            return

        self.send_response(404)
        self.end_headers()

    def _send_html(self, body: str) -> None:
        self._send_bytes(body.encode("utf-8"), "text/html; charset=utf-8")

    def _send_bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


@contextlib.contextmanager
def run_fixture_server():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        host, port = probe.getsockname()

    server = ThreadingHTTPServer((host, port), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
