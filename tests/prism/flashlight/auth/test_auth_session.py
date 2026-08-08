import pytest

from prism.flashlight.auth.errors import AuthError
from prism.flashlight.auth.session import (
    MIN_REFRESH_DELAY_SECONDS,
    Session,
    parse_session_response,
)

# A real response from POST /v1/auth/anonymous/login, with the session id replaced
VALID_RESPONSE = {
    "sessionId": "flsess_bm90LWEtcmVhbC1zZXNzaW9uLWlkLW9idmlvdXNsee8",
    "tier": "anonymous",
    "expiresInSeconds": 3600,
    "refreshUntilInSeconds": 7200,
    "refreshInSeconds": 3300,
    "canRefresh": True,
}


def test_parse_session_response() -> None:
    assert parse_session_response(VALID_RESPONSE) == Session(
        session_id="flsess_bm90LWEtcmVhbC1zZXNzaW9uLWlkLW9idmlvdXNsee8",
        tier="anonymous",
        can_refresh=True,
        refresh_in_seconds=3300.0,
    )


def test_parse_session_response_cannot_refresh() -> None:
    session = parse_session_response({**VALID_RESPONSE, "canRefresh": False})
    assert not session.can_refresh


def test_parse_session_response_ignores_informational_fields() -> None:
    """Only refreshInSeconds is acted on, so the others may be anything"""
    session = parse_session_response(
        {**VALID_RESPONSE, "expiresInSeconds": "?", "refreshUntilInSeconds": None},
    )
    assert session.refresh_in_seconds == 3300.0


@pytest.mark.parametrize("refresh_in_seconds", (0, 1, 59, 59.9))
def test_parse_session_response_clamps_short_refresh_delays(
    refresh_in_seconds: float,
) -> None:
    """A server bug must not be able to turn the auth thread into a hot loop"""
    session = parse_session_response(
        {**VALID_RESPONSE, "refreshInSeconds": refresh_in_seconds},
    )
    assert session.refresh_in_seconds == MIN_REFRESH_DELAY_SECONDS


@pytest.mark.parametrize(
    "response_json",
    (
        # Not a dict
        None,
        [],
        "session",
        # Bad sessionId
        {**VALID_RESPONSE, "sessionId": ""},
        {**VALID_RESPONSE, "sessionId": None},
        {**VALID_RESPONSE, "sessionId": 123},
        # Bad tier
        {**VALID_RESPONSE, "tier": ""},
        {**VALID_RESPONSE, "tier": None},
        {**VALID_RESPONSE, "tier": 1},
        # Bad canRefresh
        {**VALID_RESPONSE, "canRefresh": None},
        {**VALID_RESPONSE, "canRefresh": "true"},
        {**VALID_RESPONSE, "canRefresh": 1},
        # Bad refreshInSeconds
        {**VALID_RESPONSE, "refreshInSeconds": None},
        {**VALID_RESPONSE, "refreshInSeconds": "3300"},
        {**VALID_RESPONSE, "refreshInSeconds": True},
        {**VALID_RESPONSE, "refreshInSeconds": -1},
        {**VALID_RESPONSE, "refreshInSeconds": float("inf")},
        {**VALID_RESPONSE, "refreshInSeconds": float("nan")},
    ),
)
def test_parse_session_response_invalid(response_json: object) -> None:
    with pytest.raises(AuthError):
        parse_session_response(response_json)
