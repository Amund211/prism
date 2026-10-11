import hmac
import html
import http.server
import logging
import string
import threading
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Literal, Self

logger = logging.getLogger(__name__)

CALLBACK_PATH = "/callback"

# How long close() can wait for the serve loop to notice
POLL_INTERVAL_SECONDS = 0.5

# NOTE: The callback's query holds the result token. Never log a request line.


@dataclass(frozen=True, slots=True)
class Callback:
    """What flashlight sent back: a result token, or an error code"""

    result: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class Page:
    """What the browser's page shows"""

    heading: str
    message: str
    badge: Literal["check", "cross"] | None = None


_BADGES = {
    "check": """<div class="badge check"><svg width="28" height="28" \
viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" \
stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">\
<path d="M5 12.5l4.5 4.5L19 7.5"/></svg></div>""",
    "cross": """<div class="badge cross"><svg width="28" height="28" \
viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" \
stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">\
<path d="M7 7l10 10M17 7L7 17"/></svg></div>""",
}

# Self-contained: served offline from the loopback server
_PAGE = string.Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>$title</title>
<style>
:root {
  --bg: #0f1115;
  --text: #ffffff;
  --dim: #9aa3b2;
  --win: #4ade80;
  --loss: #f87171;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f5f6f8;
    --text: #1a1d24;
    --dim: #5b6473;
    --win: #16a34a;
    --loss: #dc2626;
  }
}
*, *::before, *::after { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--bg);
  font-family: Roboto, system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
}
.strip {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(
    90deg, #ef4444, #f59e0b, #eab308, #22c55e, #06b6d4, #6366f1, #a855f7
  );
}
main {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  max-width: 380px;
  text-align: center;
}
.badge {
  --tone: var(--win);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  color: var(--tone);
  background: color-mix(in srgb, var(--tone) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--tone) 40%, transparent);
}
.badge.cross { --tone: var(--loss); }
.text { display: flex; flex-direction: column; gap: 8px; }
h1 { margin: 0; font-size: 22px; font-weight: 600; color: var(--text); }
p {
  margin: 0;
  font-size: 15px;
  line-height: 1.5;
  color: var(--dim);
  text-wrap: pretty;
}
</style>
</head>
<body>
<div class="strip"></div>
<main>
$badge
<div class="text">
<h1>$heading</h1>
<p>$message</p>
</div>
</main>
</body>
</html>
""")


def render_page(page: Page) -> str:
    return _PAGE.substitute(
        title=html.escape(f"{page.heading} · Prism"),
        badge="" if page.badge is None else _BADGES[page.badge],
        heading=html.escape(page.heading),
        message=html.escape(page.message),
    )


class _Server(http.server.ThreadingHTTPServer):
    def __init__(self, listener: "LoopbackListener") -> None:
        self.listener = listener
        super().__init__(("127.0.0.1", 0), _Handler)


class _Handler(http.server.BaseHTTPRequestHandler):
    server: _Server

    # Bounds a connection that sends nothing, such as a browser's preconnect
    timeout = 5

    def do_GET(self) -> None:
        url = urllib.parse.urlsplit(self.path)
        if url.path != CALLBACK_PATH:
            self._respond(404, Page("Not found", ""))
            return

        page = self.server.listener._accept(dict(urllib.parse.parse_qsl(url.query)))
        if page is None:
            self._respond(400, Page("Bad request", ""))
            return

        self._respond(200, page)

    def _respond(self, status: int, page: Page) -> None:
        body = render_page(page).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # The page's own URL holds the result token
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # The default logs the request line, which holds the result token
        pass


class LoopbackListener:
    """
    A one-shot HTTP listener on 127.0.0.1 for flashlight's sign-in callback

    Use as a context manager: it serves from `__enter__` and is closed on exit.
    Only `GET /callback` with the expected `state` ends the wait. Anything else,
    from another local process or a web page probing the port, is refused.
    A local process can still bind the same port on Windows and take the
    callback; PKCE makes the result token useless to it.
    """

    def __init__(self, *, state: str, describe: Callable[[Callback], Page]) -> None:
        """`describe` gives the browser's page"""
        self._state = state
        self._describe = describe
        self._lock = threading.Lock()
        self._finished = threading.Event()
        self._callback: Callback | None = None
        self._serving = False
        self._closed = False
        self._server = _Server(self)

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def callback_url(self) -> str:
        """The `return` url for flashlight"""
        return f"http://127.0.0.1:{self.port}{CALLBACK_PATH}"

    def __enter__(self) -> Self:
        threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": POLL_INTERVAL_SECONDS},
            daemon=True,
            name="prism-ms-loopback",
        ).start()
        self._serving = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def wait(self, timeout: float) -> Callback | None:
        """Return the callback, or None on a timeout or a cancel"""
        self._finished.wait(timeout)
        with self._lock:
            return self._callback

    def cancel(self) -> None:
        """End the wait without a callback"""
        self._finished.set()

    def close(self) -> None:
        """Stop serving and close the socket"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._finished.set()
        if self._serving:
            self._server.shutdown()
        self._server.server_close()

    def _accept(self, query: dict[str, str]) -> Page | None:
        """Take a callback, and return the page, or None to refuse it"""
        state = query.get("state", "")
        if not hmac.compare_digest(state.encode(), self._state.encode()):
            return None

        error, result = query.get("error"), query.get("result")
        if error:
            callback = Callback(result=None, error=error)
        elif result:
            callback = Callback(result=result, error=None)
        else:
            return None

        with self._lock:
            if self._callback is None and not self._finished.is_set():
                self._callback = callback
                self._finished.set()

        return self._describe(callback)
