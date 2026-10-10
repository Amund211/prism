import socket
import threading
from collections.abc import Iterator

import pytest
import requests

from prism.flashlight.auth import loopback
from prism.flashlight.auth.loopback import Callback, LoopbackListener

STATE = "the-expected-state"


def describe(callback: Callback) -> str:
    if callback.error is not None:
        return f"<failed: {callback.error}>"
    return "Signed in"


@pytest.fixture(autouse=True)
def fast_close(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loopback, "POLL_INTERVAL_SECONDS", 0.01)


@pytest.fixture
def http() -> Iterator[requests.Session]:
    with requests.Session() as session:
        # Never route loopback requests through a proxy from the environment
        session.trust_env = False
        yield session


@pytest.fixture
def listener() -> Iterator[LoopbackListener]:
    with LoopbackListener(state=STATE, describe=describe) as listener:
        yield listener


def get(
    http: requests.Session, listener: LoopbackListener, path: str
) -> requests.Response:
    return http.get(f"http://127.0.0.1:{listener.port}{path}", timeout=5)


def assert_closed(port: int) -> None:
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()


def test_callback_url(listener: LoopbackListener) -> None:
    assert listener.callback_url == f"http://127.0.0.1:{listener.port}/callback"


def test_returns_the_result(http: requests.Session, listener: LoopbackListener) -> None:
    response = get(http, listener, f"/callback?result=the-result&state={STATE}")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert "Signed in" in response.text
    assert listener.wait(5) == Callback(result="the-result", error=None)


def test_returns_the_error(http: requests.Session, listener: LoopbackListener) -> None:
    response = get(http, listener, f"/callback?error=no_game&state={STATE}")

    assert response.status_code == 200
    assert "&lt;failed: no_game&gt;" in response.text
    assert listener.wait(5) == Callback(result=None, error="no_game")


@pytest.mark.parametrize("path", ["/", "/favicon.ico", f"/callbacks?state={STATE}"])
def test_ignores_other_paths(
    http: requests.Session, listener: LoopbackListener, path: str
) -> None:
    assert get(http, listener, path).status_code == 404
    assert listener.wait(0) is None

    get(http, listener, f"/callback?result=the-result&state={STATE}")
    assert listener.wait(5) == Callback(result="the-result", error=None)


@pytest.mark.parametrize(
    "query",
    [
        "result=the-result",
        "result=the-result&state=",
        "result=the-result&state=wrong",
        f"result=the-result&state={STATE}x",
        f"state={STATE}",
        f"result=&state={STATE}",
    ],
)
def test_ignores_wrong_state_and_missing_values(
    http: requests.Session, listener: LoopbackListener, query: str
) -> None:
    response = get(http, listener, f"/callback?{query}")

    assert response.status_code == 400
    assert "the-result" not in response.text
    assert listener.wait(0) is None


def test_accepts_only_get(http: requests.Session, listener: LoopbackListener) -> None:
    response = http.post(
        f"{listener.callback_url}?result=the-result&state={STATE}", timeout=5
    )

    assert response.status_code == 501
    assert listener.wait(0) is None


def test_keeps_the_first_callback(
    http: requests.Session, listener: LoopbackListener
) -> None:
    get(http, listener, f"/callback?result=first&state={STATE}")
    get(http, listener, f"/callback?error=no_game&state={STATE}")

    assert listener.wait(5) == Callback(result="first", error=None)


def test_an_idle_connection_does_not_block_the_callback(
    http: requests.Session, listener: LoopbackListener
) -> None:
    """A browser's preconnect, or a local probe, sends nothing"""
    with socket.create_connection(("127.0.0.1", listener.port)):
        get(http, listener, f"/callback?result=the-result&state={STATE}")

        assert listener.wait(5) == Callback(result="the-result", error=None)


def test_times_out_and_closes() -> None:
    with LoopbackListener(state=STATE, describe=describe) as listener:
        assert listener.wait(0.01) is None

    assert_closed(listener.port)


def test_cancel_ends_the_wait_and_closes() -> None:
    with LoopbackListener(state=STATE, describe=describe) as listener:
        threading.Timer(0.05, listener.cancel).start()

        assert listener.wait(5) is None

    assert_closed(listener.port)


def test_closes_after_a_callback(
    http: requests.Session, listener: LoopbackListener
) -> None:
    get(http, listener, f"/callback?result=the-result&state={STATE}")
    listener.close()

    assert_closed(listener.port)
