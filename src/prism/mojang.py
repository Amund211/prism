import functools
import threading
from json import JSONDecodeError

import requests
from requests.exceptions import RequestException, SSLError

from prism.errors import APIError, PlayerNotFoundError
from prism.ratelimiting import RateLimiter
from prism.requests import make_prism_requests_session
from prism.retry import ExecutionError, execute_with_retry
from prism.ssl_errors import MissingLocalIssuerSSLError, is_missing_local_issuer_error

USERPROFILES_ENDPOINT = "https://api.mojang.com/users/profiles/minecraft"
REQUEST_LIMIT, REQUEST_WINDOW = 600, 10 * 60  # Max requests per time window
BURST_REQUEST_LIMIT, BURST_REQUEST_WINDOW = 50, 8  # Found by trial and error


class MojangAccountProvider:
    def __init__(self, *, retry_limit: int, initial_timeout: float) -> None:
        self._retry_limit = retry_limit
        self._initial_timeout = initial_timeout

        # Use a connection pool for the requests
        self._session = make_prism_requests_session()

        # Be nice to the Mojang api :)
        self._limiter = RateLimiter(limit=REQUEST_LIMIT, window=REQUEST_WINDOW)
        self._burst_limiter = RateLimiter(
            limit=BURST_REQUEST_LIMIT, window=BURST_REQUEST_WINDOW
        )

        # TODO: implement a disk cache
        # TTL on this cache can be large because for a username to get a new uuid the
        # user must first change their ign, then, after 37 days, someone else can get
        # the name
        # Mapping username.lower() -> uuid
        self._lowercase_uuid_cache: dict[str, str] = {}
        self._uuid_cache_mutex = threading.Lock()

    def _make_request(
        self, *, username: str, last_try: bool
    ) -> requests.Response:  # pragma: nocover
        try:
            # Uphold our prescribed rate-limits
            with self._limiter, self._burst_limiter:
                response = self._session.get(f"{USERPROFILES_ENDPOINT}/{username}")
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
            raise ExecutionError(
                "Request to Mojang API failed due to rate limit, retrying"
            )

        return response

    def get_uuid_for_username(self, username: str, /) -> str:  # pragma: nocover
        """Get the uuid of the user"""
        with self._uuid_cache_mutex:
            cache_hit = self._lowercase_uuid_cache.get(username.lower(), None)

        if cache_hit is not None:
            return cache_hit

        try:
            response = execute_with_retry(
                functools.partial(self._make_request, username=username),
                retry_limit=self._retry_limit,
                initial_timeout=self._initial_timeout,
            )
        except ExecutionError as e:
            raise APIError(f"Request to Mojang API failed for {username=}.") from e

        if response.status_code == 404 or response.status_code == 204:
            # Not found
            raise PlayerNotFoundError(
                f"Player with username {username} not found from Mojang API."
            )

        if not response:
            raise APIError(
                "Request to Mojang API failed with status code "
                f"{response.status_code}. Response: {response.text}"
            )

        try:
            response_json = response.json()
        except JSONDecodeError as e:
            raise APIError(
                "Failed parsing the response from the Mojang API. "
                f"Raw content: {response.text}"
            ) from e

        # reponse is {"id": "...", "name": "..."}
        uuid = response_json.get("id", None)

        if not isinstance(uuid, str):
            raise APIError(
                f"Request to Mojang API returned wrong type for uuid {uuid=}"
            )

        # Set cache
        with self._uuid_cache_mutex:
            self._lowercase_uuid_cache[username.lower()] = uuid

        return uuid
