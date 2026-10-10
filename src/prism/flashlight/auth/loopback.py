import hmac
import html
import http.server
import logging
import threading
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Self

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


_PAGE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Prism</title></head>
<body style="font-family: sans-serif; text-align: center; margin-top: 4em">
<h1>Prism</h1>
<p>{message}</p>
</body>
</html>
"""


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
            self._respond(404, "Not found")
            return

        message = self.server.listener._accept(dict(urllib.parse.parse_qsl(url.query)))
        if message is None:
            self._respond(400, "Bad request")
            return

        self._respond(200, message)

    def _respond(self, status: int, message: str) -> None:
        body = _PAGE.format(message=html.escape(message)).encode("utf-8")
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

    def __init__(self, *, state: str, describe: Callable[[Callback], str]) -> None:
        """`describe` gives the message for the browser's page"""
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

    def _accept(self, query: dict[str, str]) -> str | None:
        """Take a callback, and return the page's message, or None to refuse it"""
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
