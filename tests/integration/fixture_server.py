from __future__ import annotations

import contextlib
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


STATIC_PAGE = """<!doctype html>
<html><body><main><h1>Static Fixture</h1><p>Static content.</p></main></body></html>
"""

DYNAMIC_PAGE = """<!doctype html>
<html>
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


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/static":
            body = STATIC_PAGE
        elif self.path == "/dynamic":
            body = DYNAMIC_PAGE
        elif self.path == "/lazy":
            body = LAZY_PAGE
        else:
            self.send_response(404)
            self.end_headers()
            return

        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

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

