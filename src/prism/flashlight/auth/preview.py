import http.server
import json
import secrets
import threading
import urllib.parse
from dataclasses import dataclass
from types import TracebackType
from typing import Self

from prism.flashlight.auth.loopback import LoopbackListener
from prism.flashlight.auth.signin import _ERROR_MESSAGES, _describe


@dataclass(frozen=True, slots=True)
class PreviewState:
    """One state of the sign-in page, served by the real loopback listener"""

    label: str
    url: str
    status: int


def _states(listener: LoopbackListener, state: str) -> tuple[PreviewState, ...]:
    def callback(**query: str) -> str:
        return f"{listener.callback_url}?{urllib.parse.urlencode(query)}"

    codes_by_message: dict[str, list[str]] = {}
    for code, message in _ERROR_MESSAGES.items():
        codes_by_message.setdefault(message, []).append(code)

    return (
        PreviewState("Success", callback(state=state, result="preview"), 200),
        *(
            PreviewState(
                f"Error: {', '.join(codes)}", callback(state=state, error=codes[0]), 200
            )
            for codes in codes_by_message.values()
        ),
        PreviewState(
            "Error: unknown code", callback(state=state, error="preview_unknown"), 200
        ),
        PreviewState("404 Not found", f"http://127.0.0.1:{listener.port}/", 404),
        PreviewState("400 Bad request", callback(state="wrong", result="preview"), 400),
    )


_PANEL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Sign-in page preview · Prism</title>
<style>
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body {
  display: flex;
  font: 13px system-ui, sans-serif;
  background: #1b1d22;
  color: #d8dce3;
}
nav {
  width: 260px;
  flex: none;
  padding: 12px;
  overflow-y: auto;
  border-right: 1px solid #333;
}
h2 {
  margin: 16px 0 6px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #8a909c;
}
h2:first-child { margin-top: 0; }
button {
  display: block;
  width: 100%;
  margin: 2px 0;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
button:hover { background: #2a2d34; }
button[aria-pressed="true"] { background: #2f3644; border-color: #4b5a75; }
.row { display: flex; gap: 4px; }
.row button { text-align: center; }
.status { color: #8a909c; float: right; }
a { color: #7aa7ff; }
main {
  flex: 1;
  display: flex;
  justify-content: center;
  background: repeating-conic-gradient(#202228 0 25%, #1b1d22 0 50%) 0 0 / 16px 16px;
}
iframe { width: 100%; height: 100%; border: 0; background: transparent; }
iframe.phone { width: 375px; border: solid #333; border-width: 0 1px; }
</style>
</head>
<body>
<nav>
<h2>State</h2>
<div id="states"></div>
<h2>Theme</h2>
<div class="row" id="themes">
<button data-theme="">System</button>
<button data-theme="dark">Dark</button>
<button data-theme="light">Light</button>
</div>
<h2>Width</h2>
<div class="row" id="widths">
<button data-width="">Full</button>
<button data-width="phone">Phone</button>
</div>
<h2>Page</h2>
<a id="open" target="_blank">Open on its own</a>
</nav>
<main><iframe id="frame" title="Sign-in page"></iframe></main>
<script>
const STATES = $states;
const frame = document.getElementById("frame");
const open = document.getElementById("open");
const pick = (group, button) => {
  for (const b of group.querySelectorAll("button")) {
    b.setAttribute("aria-pressed", String(b === button));
  }
};
const states = document.getElementById("states");
STATES.forEach((s, i) => {
  const b = document.createElement("button");
  b.textContent = s.label;
  const status = document.createElement("span");
  status.className = "status";
  status.textContent = s.status;
  b.append(status);
  b.onclick = () => { pick(states, b); frame.src = s.url; open.href = s.url; };
  states.append(b);
  if (i === 0) b.click();
});
const themes = document.getElementById("themes");
for (const b of themes.querySelectorAll("button")) {
  // The framed page's prefers-color-scheme follows the iframe's color-scheme
  b.onclick = () => { pick(themes, b); frame.style.colorScheme = b.dataset.theme; };
}
themes.querySelector("button").click();
const widths = document.getElementById("widths");
for (const b of widths.querySelectorAll("button")) {
  b.onclick = () => { pick(widths, b); frame.className = b.dataset.width; };
}
widths.querySelector("button").click();
</script>
</body>
</html>
"""


def _render_panel(states: tuple[PreviewState, ...]) -> str:
    data = json.dumps(
        [{"label": s.label, "url": s.url, "status": s.status} for s in states]
    )
    # Inside <script>, only "</script>" can break out
    return _PANEL.replace("$states", data.replace("<", "\\u003c"))


class _PanelServer(http.server.ThreadingHTTPServer):
    def __init__(self, panel: str) -> None:
        self.panel = panel.encode("utf-8")
        super().__init__(("127.0.0.1", 0), _PanelHandler)


class _PanelHandler(http.server.BaseHTTPRequestHandler):
    server: _PanelServer

    def do_GET(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.server.panel)))
        self.end_headers()
        self.wfile.write(self.server.panel)

    def log_message(self, format: str, *args: object) -> None:
        pass


class PreviewServer:
    """
    A control panel that frames every state of the sign-in callback page

    The pages come from a real LoopbackListener, so they match a real sign-in.
    Use as a context manager.
    """

    def __init__(self) -> None:
        state = secrets.token_urlsafe(16)
        self._listener = LoopbackListener(state=state, describe=_describe)
        self.states = _states(self._listener, state)
        self._panel = _PanelServer(_render_panel(self.states))

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._panel.server_address[1]}/"

    def __enter__(self) -> Self:
        self._listener.__enter__()
        threading.Thread(
            target=self._panel.serve_forever,
            daemon=True,
            name="prism-signin-preview",
        ).start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._panel.shutdown()
        self._panel.server_close()
        self._listener.close()
