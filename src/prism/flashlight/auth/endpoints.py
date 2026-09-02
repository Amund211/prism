import logging
from json import JSONDecodeError
from typing import Any

import requests
from requests.exceptions import RequestException

from prism.flashlight.auth.errors import (
    AuthError,
    RefreshRateLimitedError,
    SessionExpiredError,
)
from prism.flashlight.auth.proof_of_work import Challenge, parse_challenge_response
from prism.flashlight.auth.session import Session, parse_session_response
from prism.flashlight.headers import make_flashlight_client_headers
from prism.flashlight.url import FLASHLIGHT_API_URL

logger = logging.getLogger(__name__)

AUTH_TIMEOUT_SECONDS = 10

# NOTE: Auth responses carry the session id, which is a bearer token. Never log
#       a response body from these endpoints - status codes only.


def _post_json(
    requests_session: requests.Session,
    *,
    path: str,
    body: dict[str, str],
    headers: dict[str, str],
) -> requests.Response:  # pragma: nocover
    # NOTE: The flashlight API does **not** allow third-party access.
    #       Do not send any requests to any endpoints without explicit permission.
    #       Reach out on Discord for more information. https://discord.gg/k4FGUnEHYg
    try:
        return requests_session.post(
            f"{FLASHLIGHT_API_URL}{path}",
            # Sets Content-Type: application/json, which both anonymous
            # endpoints require.
            json=body,
            headers=headers,
            timeout=AUTH_TIMEOUT_SECONDS,
        )
    except RequestException as e:
        raise AuthError(f"Request to {path} failed") from e


def _parse_json(response: requests.Response, *, path: str) -> Any:  # pragma: nocover
    try:
        return response.json()
    except JSONDecodeError as e:
        raise AuthError(f"Failed parsing the response from {path}") from e


def request_challenge(
    *,
    requests_session: requests.Session,
    user_id: str,
) -> Challenge:  # pragma: nocover
    """Ask flashlight for a proof-of-work challenge to log in as `user_id`"""
    path = "/v1/auth/anonymous/challenge"
    response = _post_json(
        requests_session,
        path=path,
        body={"userId": user_id},
        headers={
            # Sent so that the operator's user id blocklist also covers logins,
            # and so the server can price the work by client type. The challenge
            # is bound to the userId in the *body*, not to this header.
            "X-User-Id": user_id,
            **make_flashlight_client_headers(),
        },
    )

    if not response.ok:
        raise AuthError(
            f"Failed getting a proof-of-work challenge, "
            f"status code {response.status_code}"
        )

    return parse_challenge_response(_parse_json(response, path=path))


def anonymous_login(
    *,
    requests_session: requests.Session,
    user_id: str,
    challenge: str,
    solution: str,
) -> Session:  # pragma: nocover
    """
    Exchange a solved challenge for a session

    `user_id` must be byte for byte the value sent to `request_challenge` - the
    server compares them, and a mismatch is a 403 no retry can fix.
    """
    path = "/v1/auth/anonymous/login"
    response = _post_json(
        requests_session,
        path=path,
        body={"userId": user_id, "challenge": challenge, "solution": solution},
        headers={"X-User-Id": user_id, **make_flashlight_client_headers()},
    )

    if not response.ok:
        # 403 is every verification failure at once - expired challenge, an IP
        # that changed mid-handshake, insufficient work. They all want the same
        # thing: a fresh challenge, after a backoff.
        raise AuthError(f"Anonymous login failed, status code {response.status_code}")

    return parse_session_response(_parse_json(response, path=path))


def refresh_session(
    session_id: str,
    *,
    requests_session: requests.Session,
) -> Session:  # pragma: nocover
    """
    Extend the given session

    Tier-agnostic: the server branches on the stored session, so this is the
    same call whichever `LoginMethod` established it. The returned session
    replaces the one we hold whole - the id is opaque, and whether it is the same
    one is the server's business, not ours.
    """
    path = "/v1/auth/refresh"
    response = _post_json(
        requests_session,
        path=path,
        body={},
        headers={
            "Authorization": f"Bearer {session_id}",
            **make_flashlight_client_headers(),
        },
    )

    if response.status_code == 401:
        raise SessionExpiredError(
            "Flashlight will not refresh this session - it is finished"
        )

    if response.status_code == 429:
        # The endpoint's per-IP rate limit, and nothing else since the server
        # dropped its minimum refresh interval. The limiters answer ahead of the
        # handler that reads the bearer, so this says nothing about our session.
        raise RefreshRateLimitedError("Flashlight rate limited the refresh request")

    if not response.ok:
        raise AuthError(f"Session refresh failed, status code {response.status_code}")

    return parse_session_response(_parse_json(response, path=path))
