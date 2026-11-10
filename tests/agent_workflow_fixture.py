"""Deterministic, loopback-only pages for the agent workflow benchmark."""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlparse


def document(content: str, script: str = "") -> str:
    # Unrelated but accessible content makes over-capture visible in the baseline.
    navigation = "".join(f'<a href="#help-{i}">Reference topic {i}</a> ' for i in range(80))
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
    <title>Local Agent Workflow</title><style>body {{font: 16px sans-serif}}
    nav {{height: 90px; overflow: auto}} label {{display:block}}</style>
    <nav aria-label="Reference">{navigation}</nav>
    <main aria-label="Task">{content}</main><script>{script}</script></html>"""


ACCOUNT = document("""
    <h1>Test account</h1><dl><dt>Account</dt><dd id="account">fixture-user</dd>
    <dt>Plan</dt><dd id="plan">Research</dd><dt>Credits</dt><dd id="credits">42</dd></dl>
""")

FORM = document(
    """<h1>Local draft</h1><form onsubmit="event.preventDefault()">
    <label>Name <input aria-label="Name"></label>
    <label>Region <select aria-label="Region"><option>Choose</option>
    <option>North</option><option>South</option></select></label>
    <p id="availability">Choose a region</p>
    <button type="button" id="preview">Preview draft</button></form>
    <p role="status" id="result"></p>""",
    """document.querySelector('select').onchange = () => {
      document.querySelector('#availability').textContent = 'Loading options';
      setTimeout(() => { document.querySelector('#availability').textContent = 'North ready'; }, 120);
    };
    document.querySelector('#preview').onclick = () => {
      document.querySelector('#result').textContent =
        document.querySelector('input').value + ' / ' + document.querySelector('select').value;
    };""",
)

LIST = document(
    """<h1>Local catalog</h1><p id="page-label"></p><table aria-label="Catalog">
    <thead><tr><th>Item</th><th>Price</th></tr></thead><tbody></tbody></table>
    <button id="next">Next page</button>""",
    """let index = 0;
    function render() {
      document.querySelector('#page-label').textContent = 'Page ' + (index + 1);
      document.querySelector('tbody').innerHTML = Array.from({length: 4}, (_, i) => {
        const n = index * 4 + i + 1;
        return '<tr><td>Item ' + n + '</td><td>' + n * 3 + '</td></tr>';
      }).join('');
      document.querySelector('#next').disabled = index === 2;
    }
    document.querySelector('#next').onclick = () => { index += 1; setTimeout(render, 90); };
    render();""",
)

RESILIENCE = document(
    """<h1>Recovery fixture</h1><div id="target"><button id="original">Original action</button></div>
    <button id="replace">Replace target</button><button id="later">Reveal later</button>
    <a href="/account" id="navigate">Account page</a><p id="marker">unchanged</p>""",
    """document.querySelector('#replace').onclick = () => {
      document.querySelector('#target').innerHTML = '<button>Changed action</button>';
    };
    document.querySelector('#later').onclick = () => {
      setTimeout(() => {
        const button = document.createElement('button'); button.textContent = 'Delayed action';
        document.querySelector('#target').appendChild(button);
      }, 120);
    };""",
)

PAGES = {"/account": ACCOUNT, "/form": FORM, "/list": LIST, "/resilience": RESILIENCE}


class WorkflowHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/seed":
            body = b"Local simulated sign-in state prepared"
            self.send_response(200)
            self.send_header(
                "Set-Cookie", "workflow-fixture=local; HttpOnly; SameSite=Strict; Path=/"
            )
        elif path == "/account" and "workflow-fixture=local" not in self.headers.get("Cookie", ""):
            body = b"Sign in required"
            self.send_response(401)
        elif path in PAGES:
            body = PAGES[path].encode("utf-8")
            self.send_response(200)
        else:
            body = b"Not found"
            self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # Fixtures have no network dependencies, even if page markup changes later.
        self.send_header(
            "Content-Security-Policy", "default-src 'self' 'unsafe-inline'; connect-src 'none'"
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        pass


@contextmanager
def workflow_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), WorkflowHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
