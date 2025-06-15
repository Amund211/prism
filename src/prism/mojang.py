import functools
import threading
from json import JSONDecodeError

import requests
from requests.exceptions import RequestException, SSLError

from prism.ratelimiting import RateLimiter
from prism.requests import make_prism_requests_session
from prism.retry import ExecutionError, execute_with_retry
from prism.ssl_errors import MissingLocalIssuerSSLError, is_missing_local_issuer_error

USERPROFILES_ENDPOINT = "https://api.mojang.com/users/profiles/minecraft"
REQUEST_LIMIT, REQUEST_WINDOW = 600, 10 * 60  # Max requests per time window
BURST_REQUEST_LIMIT, BURST_REQUEST_WINDOW = 50, 8  # Found by trial and error

# Use a connection pool for the requests
SESSION = make_prism_requests_session()


class MojangAPIError(ValueError):
    """Exception raised when we receive an error from the Mojang api"""


# Be nice to the Mojang api :)
limiter = RateLimiter(limit=REQUEST_LIMIT, window=REQUEST_WINDOW)
burst_limiter = RateLimiter(limit=BURST_REQUEST_LIMIT, window=BURST_REQUEST_WINDOW)

# TODO: implement a disk cache
# TTL on this cache can be large because for a username to get a new uuid the user
# must first change their ign, then, after 37 days, someone else can get the name
LOWERCASE_UUID_CACHE: dict[str, str] = {}  # Mapping username.lower() -> uuid
UUID_MUTEX = threading.Lock()


def compare_uuids(uuid_1: str, uuid_2: str, /) -> bool:
    """Return True if the two uuids (dashed or not) are equal"""
    return uuid_1.replace("-", "") == uuid_2.replace("-", "")


def _make_request(
    *, username: str, last_try: bool
) -> requests.Response:  # pragma: nocover
    try:
        # Uphold our prescribed rate-limits
        with limiter, burst_limiter:
            # response = SESSION.get(f"{USERPROFILES_ENDPOINT}/{username}")
            response = SESSION.get(f"{'https://api.minetools.eu'}/uuid/{username}")
    except SSLError as e:
        if is_missing_local_issuer_error(e):
            # Short circuit out of get_uuid
            # NOTE: Remember to catch this exception in the caller
            raise MissingLocalIssuerSSLError(
                "Request to Mojang API failed due to missing local issuer cert"
            ) from e
        raise ExecutionError(
            "Request to Mojang API failed due to an unknown SSL error"
        ) from e
    except RequestException as e:
        raise ExecutionError(
            "Request to Mojang API failed due to an unknown error"
        ) from e

    if (
        response.status_code == 429
        or response.status_code == 503
        or response.status_code == 504
    ) and not last_try:
        raise ExecutionError("Request to Mojang API failed due to rate limit, retrying")

    return response


def get_uuid(
    username: str, retry_limit: int = 5, initial_timeout: float = 2
) -> str | None:  # pragma: nocover
    """Get the uuid of the user. None if not found."""
    with UUID_MUTEX:
        cache_hit = LOWERCASE_UUID_CACHE.get(username.lower(), None)

    if cache_hit is not None:
        return cache_hit

    try:
        response = execute_with_retry(
            functools.partial(_make_request, username=username),
            retry_limit=retry_limit,
            initial_timeout=initial_timeout,
        )
    except ExecutionError as e:
        raise MojangAPIError(f"Request to Mojang API failed for {username=}.") from e

    if response.status_code == 404 or response.status_code == 204:
        # Not found
        return None

    if not response:
        raise MojangAPIError(
            f"Request to Mojang API failed with status code {response.status_code}. "
            f"Response: {response.text}"
        )

    try:
        response_json = response.json()
    except JSONDecodeError as e:
        raise MojangAPIError(
            "Failed parsing the response from the Mojang API. "
            f"Raw content: {response.text}"
        ) from e

    # reponse is {"id": "...", "name": "..."}
    uuid = response_json.get("id", None)

    if not isinstance(uuid, str):
        raise MojangAPIError(
            f"Request to Mojang API returned wrong type for uuid {uuid=}"
        )

    # Set cache
    with UUID_MUTEX:
        LOWERCASE_UUID_CACHE[username.lower()] = uuid

    return uuid
