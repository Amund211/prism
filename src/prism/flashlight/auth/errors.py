from prism.errors import APIError


class AuthError(Exception):
    """
    Failed to establish or maintain a flashlight auth session

    Always retryable. Every cause - a network failure, a 5xx, a 403 on the
    handshake, a difficulty we refuse to work on - gets the same treatment,
    because the client's move is the same for all of them: back off and try
    again. Retrying a cause we cannot fix costs nothing and means a server-side
    fix reaches every running overlay without a restart.
    """


class SessionExpiredError(AuthError):
    """
    The session cannot be refreshed - a full login is required

    Flashlight answers 401 to /v1/auth/refresh when the session is unknown,
    revoked, past its refresh window or past its absolute lifetime cap.
    """


class RefreshRateLimitedError(AuthError):
    """
    Flashlight rate limited the refresh request (429)

    Says nothing about the session, unlike `SessionExpiredError`: the per-IP
    limiters answer ahead of the handler that reads the bearer. The session is
    untouched, so keep it and do not re-log in.
    """


class NoSessionError(APIError):
    """
    No auth session was available to make a flashlight request with

    An `APIError` so that every existing call site handles it as the failed
    request it is.
    """


class SessionRecoveryError(APIError):
    """
    A request got a 401 we cannot account for

    The counterpart to handing a 401 back to the caller, which only happens when
    the server told us it validated the bearer we sent (`X-Auth-Session`). This
    says the opposite: we do not know whose 401 it was, so a caller must not
    blame anything of its own for it. `/v1/tags/{uuid}` is why that distinction
    exists - it answers 401 for an invalid Urchin API key too, and wrongly
    latching that is sticky for the rest of the process.
    """
