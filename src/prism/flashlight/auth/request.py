from collections.abc import Callable, Mapping

import requests

from prism.flashlight.auth.errors import NoSessionError, SessionRecoveryError
from prism.flashlight.auth.manager import AuthManager
from prism.flashlight.auth.session import Session

# Set by flashlight on any response to a request that carried a valid bearer,
# once that session is due for a refresh. A hint: we act on it by waking the auth
# thread, and ignoring it would still be correct.
REFRESH_HINT_HEADER = "X-Auth-Refresh"

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

    A 401 is only ever returned to the caller when the server has vouched for the
    session we hold, which means the 401 was about something else — that is what
    lets `/v1/tags/{uuid}` interpret its own 401 for an invalid Urchin API key. A
    401 we cannot account for raises `SessionRecoveryError` instead, so no call
    site can mistake an auth problem for one of its own.

    NOTE: `send` must be safe to call twice. Every flashlight endpoint prism
          calls is a read, so replaying one is harmless.
    """
    session = auth.wait_for_session()
    if session is None:
        raise NoSessionError("No flashlight auth session available")

    response = send(bearer_headers(session))
    if response.status_code != 401:
        _note_refresh_hint(auth, session, response)
        return response

    recovery = auth.recover_from_unauthorized(session)
    if recovery.session is None:
        if recovery.session_confirmed:
            # The server refuses to replace this session, so it is fine and the
            # 401 belongs to the caller. Sending the same bearer again would only
            # reproduce it.
            return response
        raise SessionRecoveryError(
            "Got HTTP 401 from flashlight and could not renew the auth session"
        )

    # TODO: The retry's own 401 is returned with no verdict at all, which breaks
    #       the invariant this docstring promises and `tags.py` relies on. Same for
    #       the session `recover_from_unauthorized` hands back from the
    #       already-replaced branch: nothing has vouched for it. Concretely, during
    #       a flashlight rollout or with read-replica lag the first request 401s,
    #       the refresh succeeds against the primary, and the retry hits a replica
    #       that has not seen the new session and 401s again - `tags.py` then
    #       blames the Urchin API key and latches `urchin_api_key_invalid` for the
    #       rest of the process. A second 401 should raise `SessionRecoveryError`
    #       rather than reach the caller.
    response = send(bearer_headers(recovery.session))
    _note_refresh_hint(auth, recovery.session, response)
    return response


def _note_refresh_hint(
    auth: AuthManager, session: Session, response: requests.Response
) -> None:
    # Any non-empty value counts. The server sends "1" today and reserves room
    # for a richer value later, and every value means the same thing to us:
    # deal with this session now.
    if response.headers.get(REFRESH_HINT_HEADER):
        auth.note_refresh_hint(session)
