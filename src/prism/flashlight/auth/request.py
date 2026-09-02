from collections.abc import Callable, Mapping

import requests

from prism.flashlight.auth.errors import NoSessionError, SessionRecoveryError
from prism.flashlight.auth.manager import AuthManager
from prism.flashlight.auth.session import Session

# Set by flashlight on any response to a request that carried a valid bearer,
# once that session is due for a refresh. A hint: we act on it by waking the auth
# thread, and ignoring it would still be correct.
REFRESH_HINT_HEADER = "X-Auth-Refresh"

# Set by flashlight's bearer middleware on every request it handled. `valid` means
# it validated our bearer, so a 401 alongside it came from the handler.
AUTH_SESSION_HEADER = "X-Auth-Session"
AUTH_SESSION_VALID = "valid"

# Performs one HTTP request, merging in the given auth headers.
SendRequest = Callable[[Mapping[str, str]], requests.Response]


def bearer_headers(session: Session) -> dict[str, str]:
    """Return the auth headers for the given session"""
    return {"Authorization": f"Bearer {session.session_id}"}


def send_authenticated(
    *,
    auth: AuthManager,
    send: SendRequest,
) -> requests.Response:
    """
    Send a flashlight request with our bearer, recovering once from a 401

    `send` is called with the headers to merge into the request, and may be called
    twice: prism holds one session for the whole process, so a lapsed session
    means the first call 401s and the second carries a renewed bearer.

    A 401 is only ever returned to the caller when the server says it validated
    the session we sent (`X-Auth-Session: valid`), which means the 401 was about
    something else — that is what lets `/v1/tags/{uuid}` interpret its own 401 for
    an invalid Urchin API key. A 401 we cannot account for raises
    `SessionRecoveryError` instead, so no call site can mistake an auth problem
    for one of its own.

    That header is the only attribution mechanism: nothing the auth manager can
    tell us amounts to "your session is fine".

    NOTE: `send` must be safe to call twice. Every flashlight endpoint prism
          calls is a read, so replaying one is harmless.
    """
    session = auth.wait_for_session()
    if session is None:
        raise NoSessionError("No flashlight auth session available")

    response = send(bearer_headers(session))
    # Nothing here says our session is bad, so there is nothing to recover from -
    # and the hint rides a validated 401 like any other response.
    if response.status_code != 401 or _session_was_validated(response):
        _note_refresh_hint(auth, session, response)
        return response

    renewed = auth.recover_from_unauthorized(session)
    if renewed is None:
        raise SessionRecoveryError(
            "Got HTTP 401 from flashlight and could not renew the auth session"
        )

    response = send(bearer_headers(renewed))
    if response.status_code == 401 and not _session_was_validated(response):
        # A renewed bearer rejected with nothing confirming it is an auth problem,
        # not the caller's: an instance that has not seen the new session - a
        # rollout, or replica lag - looks exactly like a bad Urchin API key, and
        # `tags.py` would latch `urchin_api_key_invalid` for the process.
        raise SessionRecoveryError(
            "Got HTTP 401 from flashlight with a renewed auth session"
        )
    _note_refresh_hint(auth, renewed, response)
    return response


def _session_was_validated(response: requests.Response) -> bool:
    """Report whether the server says it validated the bearer we sent"""
    # Exact match, unlike the permissive `_note_refresh_hint` below: a hint is safe
    # to over-read, this is not. Absence means "unknown" - a stripped header, or
    # something answering ahead of the middleware - which keeps recovery.
    return response.headers.get(AUTH_SESSION_HEADER) == AUTH_SESSION_VALID


def _note_refresh_hint(
    auth: AuthManager, session: Session, response: requests.Response
) -> None:
    # Any non-empty value counts. The server sends "1" today and reserves room
    # for a richer value later, and every value means the same thing to us:
    # deal with this session now.
    if response.headers.get(REFRESH_HINT_HEADER):
        auth.note_refresh_hint(session)
