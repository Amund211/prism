import time
from collections.abc import Mapping, Sequence

import pytest
import requests

from prism.flashlight.auth.errors import (
    AuthError,
    NoSessionError,
    RefreshTooSoonError,
    SessionRecoveryError,
)
from prism.flashlight.auth.request import (
    AUTH_SESSION_HEADER,
    AUTH_SESSION_VALID,
    REFRESH_HINT_HEADER,
    bearer_headers,
    send_authenticated,
)
from tests.prism.auth_utils import (
    TEST_SESSION_ID,
    make_auth_manager,
    make_fast_forward_auth_manager,
    make_session,
    running_auth_thread,
)


def make_response(
    status_code: int,
    *,
    refresh_hint: str | None = None,
    auth_session: str | None = None,
) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    if refresh_hint is not None:
        response.headers[REFRESH_HINT_HEADER] = refresh_hint
    if auth_session is not None:
        response.headers[AUTH_SESSION_HEADER] = auth_session
    return response


class RecordingSender:
    """Records the auth headers it is called with, and returns queued responses"""

    def __init__(self, responses: Sequence[requests.Response]) -> None:
        self.responses = list(responses)
        self.auth_headers: list[Mapping[str, str]] = []

    def __call__(self, auth_headers: Mapping[str, str]) -> requests.Response:
        self.auth_headers.append(auth_headers)
        assert self.responses, "Unexpected request"
        return self.responses.pop(0)


def test_bearer_headers() -> None:
    assert bearer_headers(make_session(session_id="flsess_abc")) == {
        "Authorization": "Bearer flsess_abc"
    }


def test_send_authenticated() -> None:
    manager, _, _ = make_auth_manager(login_results=[make_session()])
    manager.reconcile()
    send = RecordingSender([make_response(200)])

    response = send_authenticated(auth=manager, send=send)

    assert response.status_code == 200
    assert send.auth_headers == [{"Authorization": f"Bearer {TEST_SESSION_ID}"}]


def test_send_authenticated_without_a_session() -> None:
    """A NoSessionError is an APIError, so every call site already handles it"""
    manager = make_fast_forward_auth_manager()

    with pytest.raises(NoSessionError):
        send_authenticated(auth=manager, send=RecordingSender([]))


def test_send_authenticated_retries_once_with_a_renewed_session() -> None:
    lapsed = make_session(session_id="flsess_lapsed")
    renewed = make_session(session_id="flsess_renewed")
    manager, _, _ = make_auth_manager(login_results=[lapsed], refresh_results=[renewed])
    manager.reconcile()
    send = RecordingSender([make_response(401), make_response(200)])

    with running_auth_thread(manager):
        response = send_authenticated(auth=manager, send=send)

    assert response.status_code == 200
    assert send.auth_headers == [
        {"Authorization": "Bearer flsess_lapsed"},
        {"Authorization": "Bearer flsess_renewed"},
    ]


def test_send_authenticated_surfaces_a_401_the_server_says_is_not_ours() -> None:
    """
    /v1/tags answers 401 for an invalid Urchin API key too

    Handing the 401 back is what lets that call site tell the two apart, and it
    is also why the request is not retried with the same bearer. This is the real
    shape of that case: the 401 provokes a refresh, the server refuses to touch a
    session it considers too fresh, and so the 401 was never about the session.
    """
    session = make_session()
    manager, _, _ = make_auth_manager(
        login_results=[session], refresh_results=[RefreshTooSoonError("too soon")]
    )
    manager.reconcile()
    send = RecordingSender([make_response(401)])

    with running_auth_thread(manager):
        response = send_authenticated(auth=manager, send=send)

    assert response.status_code == 401
    assert len(send.auth_headers) == 1


def test_send_authenticated_returns_a_401_on_a_validated_session_immediately() -> None:
    """
    The server validated our session, so the 401 is the endpoint's

    `refresh_results` is empty, so any attempt to renew fails the test.

    NOTE: On the real clock, so a regression that runs recovery here times out
          rather than hanging on a frozen clock that never reaches its deadline.
    """
    manager, _, refresh = make_auth_manager(
        login_results=[make_session()], monotonic=time.monotonic
    )
    manager.reconcile()
    before = manager.seconds_until_next_action()
    send = RecordingSender([make_response(401, auth_session=AUTH_SESSION_VALID)])

    response = send_authenticated(auth=manager, send=send)

    assert response.status_code == 401
    assert len(send.auth_headers) == 1
    assert refresh.session_ids == []
    # Nothing asked the auth thread for a pass either.
    assert manager.seconds_until_next_action() == pytest.approx(before, abs=1.0)


def test_send_authenticated_acts_on_the_refresh_hint_on_a_validated_401() -> None:
    """The middleware sets both headers on the same response"""
    session = make_session()
    manager, _, _ = make_auth_manager(login_results=[session])
    manager.reconcile()
    assert manager.seconds_until_next_action() > 0

    send_authenticated(
        auth=manager,
        send=RecordingSender(
            [make_response(401, refresh_hint="1", auth_session=AUTH_SESSION_VALID)]
        ),
    )

    assert manager.seconds_until_next_action() == 0.0


def test_send_authenticated_ignores_an_unknown_auth_session_value() -> None:
    """Only `valid` counts - any other value means the same as no header at all"""
    session = make_session()
    manager, _, refresh = make_auth_manager(
        login_results=[session], refresh_results=[RefreshTooSoonError("too soon")]
    )
    manager.reconcile()
    send = RecordingSender([make_response(401, auth_session="invalid")])

    with running_auth_thread(manager):
        response = send_authenticated(auth=manager, send=send)

    assert response.status_code == 401
    assert len(send.auth_headers) == 1
    # The verdict came from the server refusing to refresh, i.e. the old path.
    assert refresh.session_ids == [TEST_SESSION_ID]


def test_send_authenticated_raises_when_the_retry_401s_unvalidated() -> None:
    """
    A renewed bearer that 401s with nothing confirming it is an auth problem

    Handing that 401 to `tags.py` would latch `urchin_api_key_invalid`.
    """
    lapsed = make_session(session_id="flsess_lapsed")
    renewed = make_session(session_id="flsess_renewed")
    manager, _, _ = make_auth_manager(login_results=[lapsed], refresh_results=[renewed])
    manager.reconcile()
    send = RecordingSender([make_response(401), make_response(401)])

    with running_auth_thread(manager):
        with pytest.raises(SessionRecoveryError):
            send_authenticated(auth=manager, send=send)

    assert len(send.auth_headers) == 2


def test_send_authenticated_returns_a_validated_401_from_the_retry() -> None:
    """The renewed session is fine, so this 401 belongs to the caller"""
    lapsed = make_session(session_id="flsess_lapsed")
    renewed = make_session(session_id="flsess_renewed")
    manager, _, _ = make_auth_manager(login_results=[lapsed], refresh_results=[renewed])
    manager.reconcile()
    send = RecordingSender(
        [make_response(401), make_response(401, auth_session=AUTH_SESSION_VALID)]
    )

    with running_auth_thread(manager):
        response = send_authenticated(auth=manager, send=send)

    assert response.status_code == 401
    assert send.auth_headers == [
        {"Authorization": "Bearer flsess_lapsed"},
        {"Authorization": "Bearer flsess_renewed"},
    ]


def test_send_authenticated_raises_on_a_401_it_cannot_account_for() -> None:
    """
    An unexplained 401 must not be passed off as the caller's

    /v1/tags would latch urchin_api_key_invalid for the rest of the process and
    stop sending a perfectly good key, so "we could not check" has to be an error
    rather than a 401 handed back.
    """
    session = make_session()
    manager, _, _ = make_auth_manager(
        login_results=[session], refresh_results=[AuthError("no network")]
    )
    manager.reconcile()
    manager.reconcile()  # fails, so we are inside the backoff with no verdict

    send = RecordingSender([make_response(401)])
    with pytest.raises(SessionRecoveryError):
        send_authenticated(auth=manager, send=send)

    assert len(send.auth_headers) == 1


def test_send_authenticated_acts_on_the_refresh_hint() -> None:
    session = make_session()
    manager, _, _ = make_auth_manager(login_results=[session])
    manager.reconcile()
    assert manager.seconds_until_next_action() > 0

    send_authenticated(
        auth=manager, send=RecordingSender([make_response(200, refresh_hint="1")])
    )

    assert manager.seconds_until_next_action() == 0.0


def test_send_authenticated_acts_on_an_unknown_refresh_hint_value() -> None:
    """Room is reserved for a richer value, and every value means "deal with it now" """
    session = make_session()
    manager, _, _ = make_auth_manager(login_results=[session])
    manager.reconcile()

    send_authenticated(
        auth=manager, send=RecordingSender([make_response(200, refresh_hint="reauth")])
    )

    assert manager.seconds_until_next_action() == 0.0


def test_send_authenticated_ignores_a_missing_refresh_hint() -> None:
    session = make_session()
    manager, _, _ = make_auth_manager(login_results=[session])
    manager.reconcile()

    send_authenticated(auth=manager, send=RecordingSender([make_response(200)]))

    assert manager.seconds_until_next_action() == session.refresh_in_seconds


def test_send_authenticated_reads_the_refresh_hint_from_the_retry() -> None:
    lapsed = make_session(session_id="flsess_lapsed")
    renewed = make_session(session_id="flsess_renewed")
    manager, _, _ = make_auth_manager(login_results=[lapsed], refresh_results=[renewed])
    manager.reconcile()
    send = RecordingSender([make_response(401), make_response(200, refresh_hint="1")])

    with running_auth_thread(manager):
        send_authenticated(auth=manager, send=send)

    assert manager.seconds_until_next_action() == 0.0
