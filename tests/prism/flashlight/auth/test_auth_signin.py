import base64
import hashlib
import os
import re
import socket
import threading
import time
import urllib.parse
import webbrowser
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import requests

from prism.flashlight.auth import loopback
from prism.flashlight.auth.credential_store import (
    CREDENTIAL_FILENAME,
    CredentialStore,
    StoredCredential,
)
from prism.flashlight.auth.errors import AuthError, CredentialRejectedError
from prism.flashlight.auth.loopback import LoopbackListener
from prism.flashlight.auth.manager import MicrosoftLoginMethod
from prism.flashlight.auth.microsoft import MicrosoftRecover
from prism.flashlight.auth.session import MicrosoftGrant, Session
from prism.flashlight.auth.signin import (
    MicrosoftSignIn,
    SignInStatus,
    error_message,
    make_pkce,
)
from prism.flashlight.url import FLASHLIGHT_API_URL
from tests.prism.auth_utils import TEST_UUID, make_auth_manager, make_session

CREDENTIAL = "C" * 43
GRANT = MicrosoftGrant(
    session=make_session(tier="microsoft"), credential=CREDENTIAL, uuid=TEST_UUID
)


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def wait_for(predicate: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, "Timed out"
        time.sleep(0.001)


class Browser:
    """A fake `open_url` that hands the start url to the test"""

    def __init__(self) -> None:
        self.urls: list[str] = []
        self.opened = threading.Event()
        self.opens: bool | Exception = True

    def __call__(self, url: str) -> bool:
        self.urls.append(url)
        self.opened.set()
        if isinstance(self.opens, Exception):
            raise self.opens
        return self.opens

    def query(self) -> dict[str, str]:
        assert self.opened.wait(5)
        return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.urls[-1]).query))

    def callback(self, **params: str) -> requests.Response:
        """Follow flashlight's redirect back to the listener"""
        query = self.query()
        params["state"] = query["state"]
        with requests.Session() as http:
            http.trust_env = False
            return http.get(query["return"], params=params, timeout=5)


class FakeExchange:
    def __init__(
        self, result: MicrosoftGrant | Exception, events: list[str] | None = None
    ) -> None:
        self.result = result
        self.events = [] if events is None else events
        self.calls: list[tuple[str, str]] = []

    def __call__(self, *, result: str, verifier: str) -> MicrosoftGrant:
        self.calls.append((result, verifier))
        self.events.append("exchange")
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class RecordingStore(CredentialStore):
    def __init__(self, path: Path, events: list[str]) -> None:
        super().__init__(path)
        self.events = events

    def write(self, stored: StoredCredential) -> None:
        self.events.append("write")
        super().write(stored)


class RecordingAuth:
    def __init__(self, store: CredentialStore, events: list[str]) -> None:
        self.store = store
        self.events = events
        self.adopted: list[tuple[Session, MicrosoftLoginMethod]] = []
        self.stored_at_adopt: StoredCredential | None = None

    def adopt(self, session: Session, login_method: MicrosoftLoginMethod) -> None:
        self.events.append("adopt")
        self.stored_at_adopt = self.store.read()
        self.adopted.append((session, login_method))


class Flow:
    def __init__(
        self,
        tmp_path: Path,
        exchange_result: MicrosoftGrant | Exception = GRANT,
        timeout_seconds: float = 5,
    ) -> None:
        self.events: list[str] = []
        self.store = RecordingStore(tmp_path / CREDENTIAL_FILENAME, self.events)
        self.exchange = FakeExchange(exchange_result, self.events)
        self.auth = RecordingAuth(self.store, self.events)
        self.browser = Browser()
        self.signin = MicrosoftSignIn(
            auth=self.auth,
            store=self.store,
            exchange=self.exchange,
            recover=self.recover,
            open_url=self.browser,
            timeout_seconds=timeout_seconds,
        )

    def recover(self, credential: str) -> MicrosoftGrant:
        raise AssertionError("Not called by the sign-in")

    def wait_until_finished(self) -> SignInStatus:
        wait_for(lambda: not self.signin.running)
        return self.signin.status

    def port(self) -> int:
        return urllib.parse.urlsplit(self.browser.query()["return"]).port or 0


@pytest.fixture(autouse=True)
def fast_close(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loopback, "POLL_INTERVAL_SECONDS", 0.01)


@pytest.fixture
def flow(tmp_path: Path) -> Iterator[Flow]:
    flow = Flow(tmp_path)
    yield flow
    flow.signin.cancel()
    flow.wait_until_finished()


def assert_closed(port: int) -> None:
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()


def test_make_pkce_matches_the_contract() -> None:
    verifier, challenge = make_pkce()

    assert re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge)
    assert challenge == b64(hashlib.sha256(verifier.encode()).digest())
    assert make_pkce()[0] != verifier


@pytest.mark.parametrize(
    "code, message",
    [
        ("client_not_approved", "Microsoft sign-in is not available yet."),
        ("no_game", "This Microsoft account does not own Minecraft Java Edition."),
        ("no_profile", "This Microsoft account does not own Minecraft Java Edition."),
        (
            "no_xbox_account",
            "This Microsoft account has no Xbox profile. "
            "Sign in once at xbox.com, then try again.",
        ),
        ("child_account", "Xbox needs an adult to approve this account."),
        (
            "adult_verification_required",
            "Xbox needs an adult to approve this account.",
        ),
        ("xbox_unavailable_in_region", "Xbox Live is not available in your region."),
        ("microsoft_error", "Sign-in was cancelled."),
        ("flow_missing", "Sign-in expired. Try again."),
        ("flow_invalid", "Sign-in expired. Try again."),
        ("flow_expired", "Sign-in expired. Try again."),
        ("state_mismatch", "Sign-in expired. Try again."),
        ("code_rejected", "Sign-in expired. Try again."),
        ("invalid_callback", "Sign-in expired. Try again."),
        ("temporarily_unavailable", "Sign-in failed. Try again later."),
        ("xbox_refused", "Sign-in failed. Try again later."),
        ("internal_error", "Sign-in failed. Try again later."),
        ("something_new", "Sign-in failed. Try again later."),
    ],
)
def test_error_message(code: str, message: str) -> None:
    assert error_message(code) == message


def test_starts_idle(flow: Flow) -> None:
    assert flow.signin.status == SignInStatus("idle")
    assert not flow.signin.running


def test_opens_the_start_url(flow: Flow) -> None:
    assert flow.signin.start()

    query = flow.browser.query()
    url = urllib.parse.urlsplit(flow.browser.urls[0])
    assert f"{url.scheme}://{url.netloc}{url.path}" == (
        f"{FLASHLIGHT_API_URL}/v1/auth/microsoft/start"
    )
    assert set(query) == {"return", "challenge", "state"}
    assert query["return"] == f"http://127.0.0.1:{flow.port()}/callback"
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", query["challenge"])
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,128}", query["state"])
    assert flow.signin.status == SignInStatus(
        "waiting_for_browser", start_url=flow.browser.urls[0]
    )
    assert flow.signin.running


def test_status_repr_hides_the_start_url() -> None:
    status = SignInStatus("waiting_for_browser", start_url="https://secret")

    assert "secret" not in repr(status)


def test_signs_in(flow: Flow) -> None:
    flow.signin.start()

    response = flow.browser.callback(result="the-result")

    assert response.status_code == 200
    # The exchange has not run yet, so the page cannot say "Signed in"
    assert "Signed in" not in response.text
    assert "close this tab and return to Prism" in response.text
    assert flow.wait_until_finished() == SignInStatus("done")
    assert flow.events == ["exchange", "write", "adopt"]

    ((result, verifier),) = flow.exchange.calls
    assert result == "the-result"
    assert b64(hashlib.sha256(verifier.encode()).digest()) == (
        flow.browser.query()["challenge"]
    )

    stored = StoredCredential(credential=CREDENTIAL, uuid=TEST_UUID)
    assert flow.auth.stored_at_adopt == stored
    ((session, login_method),) = flow.auth.adopted
    assert session is GRANT.session
    assert isinstance(login_method, MicrosoftRecover)
    assert login_method.uuid == TEST_UUID
    assert_closed(flow.port())


def test_signs_in_to_the_auth_manager(tmp_path: Path) -> None:
    manager, anonymous, _ = make_auth_manager()
    store = CredentialStore(tmp_path / CREDENTIAL_FILENAME)
    browser = Browser()
    signin = MicrosoftSignIn(
        auth=manager,
        store=store,
        exchange=FakeExchange(GRANT),
        recover=lambda credential: GRANT,
        open_url=browser,
    )

    signin.start()
    browser.callback(result="the-result")
    wait_for(lambda: not signin.running)

    assert signin.status == SignInStatus("done")
    assert manager.tier == "microsoft"
    assert manager.signed_in_uuid == TEST_UUID
    assert manager.wait_for_session(0) is GRANT.session
    assert anonymous.calls == 0


def test_callback_error(flow: Flow) -> None:
    flow.signin.start()

    response = flow.browser.callback(error="no_game")

    assert response.status_code == 200
    assert "does not own Minecraft Java Edition" in response.text
    assert flow.wait_until_finished() == SignInStatus(
        "failed", "This Microsoft account does not own Minecraft Java Edition."
    )
    assert flow.events == []
    assert flow.store.read() is None
    assert_closed(flow.port())


@pytest.mark.parametrize(
    "error, message",
    [
        (CredentialRejectedError("401"), "Sign-in expired. Try again."),
        (AuthError("status code 503"), "Sign-in failed. Try again later."),
        (ValueError("a bug"), "Sign-in failed. Try again later."),
    ],
)
def test_exchange_failure(tmp_path: Path, error: Exception, message: str) -> None:
    flow = Flow(tmp_path, exchange_result=error)
    flow.signin.start()

    flow.browser.callback(result="the-result")

    assert flow.wait_until_finished() == SignInStatus("failed", message)
    assert flow.events == ["exchange"]
    assert flow.store.read() is None


def test_failed_write_does_not_adopt(
    flow: Flow, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_replace(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail_replace)
    flow.signin.start()

    flow.browser.callback(result="the-result")

    assert flow.wait_until_finished() == SignInStatus(
        "failed", "Could not save the sign-in. Try again."
    )
    assert flow.events == ["exchange", "write"]
    assert flow.auth.adopted == []


def test_timeout_fails_and_closes(tmp_path: Path) -> None:
    flow = Flow(tmp_path, timeout_seconds=0.05)
    flow.signin.start()
    port = flow.port()

    assert flow.wait_until_finished() == SignInStatus(
        "failed", "Sign-in expired. Try again."
    )
    assert flow.events == []
    assert_closed(port)


@pytest.mark.parametrize(
    "opens", [False, webbrowser.Error("could not locate runnable browser")]
)
def test_browser_that_does_not_open_keeps_waiting_with_a_link(
    flow: Flow, opens: bool | Exception
) -> None:
    flow.browser.opens = opens
    flow.signin.start()
    flow.browser.query()

    expected = SignInStatus(
        "waiting_for_browser",
        "Could not open the browser. Copy the link into your browser.",
        start_url=flow.browser.urls[0],
    )
    wait_for(lambda: flow.signin.status == expected)

    flow.browser.callback(result="the-result")

    assert flow.wait_until_finished() == SignInStatus("done")
    assert flow.events == ["exchange", "write", "adopt"]


def test_cancel_closes(flow: Flow) -> None:
    flow.signin.start()
    port = flow.port()

    flow.signin.cancel()

    assert flow.wait_until_finished() == SignInStatus("idle")
    assert flow.events == []
    assert_closed(port)


def test_cancel_before_the_listener_is_bound(
    flow: Flow, monkeypatch: pytest.MonkeyPatch
) -> None:
    def cancel_then_bind(**kwargs: Any) -> LoopbackListener:
        flow.signin.cancel()
        return LoopbackListener(**kwargs)

    monkeypatch.setattr(
        "prism.flashlight.auth.signin.LoopbackListener", cancel_then_bind
    )
    flow.signin.start()

    assert flow.wait_until_finished() == SignInStatus("idle")
    assert flow.browser.urls == []


def test_cancel_when_idle(flow: Flow) -> None:
    flow.signin.cancel()

    assert flow.signin.status == SignInStatus("idle")


def test_refuses_a_second_start(flow: Flow) -> None:
    assert flow.signin.start()
    flow.browser.opened.wait(5)

    assert not flow.signin.start()
    assert len(flow.browser.urls) == 1


def test_can_start_again_after_a_failure(flow: Flow) -> None:
    flow.signin.start()
    flow.browser.callback(error="microsoft_error")
    flow.wait_until_finished()
    flow.browser.opened.clear()

    assert flow.signin.start()
    flow.browser.callback(result="the-result")

    assert flow.wait_until_finished() == SignInStatus("done")
    assert len(flow.browser.urls) == 2
    first, second = (
        dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        for url in flow.browser.urls
    )
    assert first["state"] != second["state"]
    assert first["challenge"] != second["challenge"]


def test_listener_failure(flow: Flow, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_bind(*args: object, **kwargs: object) -> None:
        raise OSError("no sockets for you")

    monkeypatch.setattr("prism.flashlight.auth.signin.LoopbackListener", fail_bind)
    flow.signin.start()

    assert flow.wait_until_finished() == SignInStatus(
        "failed", "Sign-in failed. Try again later."
    )
    assert flow.browser.urls == []
