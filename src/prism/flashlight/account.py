import functools
import logging
from json import JSONDecodeError

import requests
from requests.exceptions import RequestException

from prism.errors import APIError, PlayerNotFoundError
from prism.flashlight.url import FLASHLIGHT_API_URL
from prism.player import Account
from prism.ratelimiting import RateLimiter
from prism.requests import make_prism_requests_session
from prism.retry import ExecutionError, execute_with_retry
from prism.utils import is_uuid

logger = logging.getLogger(__name__)


class FlashlightAccountProvider:
    def __init__(
        self,
        *,
        retry_limit: int,
        initial_timeout: float,
    ) -> None:
        self._retry_limit = retry_limit
        self._initial_timeout = initial_timeout
        self._session = make_prism_requests_session()
        self._limiter = RateLimiter(limit=120, window=60)

    @property
    def seconds_until_unblocked(self) -> float:
        """Return the number of seconds until we are unblocked"""
        return self._limiter.block_duration_seconds

    def _make_account_by_username_request(
        self,
        *,
        url: str,
        user_id: str,
        last_try: bool,
    ) -> requests.Response:  # pragma: nocover
        try:
            # Uphold our prescribed rate-limits
            with self._limiter:
                response = self._session.get(
                    url, headers={"X-User-Id": user_id}, timeout=10
                )
        except RequestException as e:
            raise ExecutionError(
                "Request to flashlight failed due to an unknown error"
            ) from e

        if (
            response.status_code == 429 or response.status_code == 503
        ) and not last_try:
            raise ExecutionError(
                "Request to flashlight failed due to intermittent error, retrying"
            )

        return response

    def get_account_by_username(
        self,
        username: str,
        *,
        user_id: str,
    ) -> Account:  # pragma: nocover
        """Get the account information for the given username from flashlight"""
        url = f"{FLASHLIGHT_API_URL}/v1/account/username/{username}"

        try:
            response = execute_with_retry(
                functools.partial(
                    self._make_account_by_username_request,
                    url=url,
                    user_id=user_id,
                ),
                retry_limit=self._retry_limit,
                initial_timeout=self._initial_timeout,
            )
        except ExecutionError as e:
            raise APIError(f"Request to flashlight failed for {username=}.") from e

        if response.status_code == 404:
            raise PlayerNotFoundError(
                f"Player with username {username} not found from Flashlight API."
            )

        if not response:
            raise APIError(
                f"Request to flashlight failed with status code "
                f"{response.status_code} when getting account for {username=}. "
                f"Response: {response.text}"
            )

        try:
            response_json = response.json()
        except JSONDecodeError as e:
            raise APIError(
                "Failed parsing the response from flashlight. "
                f"Raw content: {response.text}"
            ) from e

        return parse_flashlight_account(response_json)


def parse_flashlight_account(response_json: object) -> Account:
    """Parse the flashlight account from the response JSON"""
    if not isinstance(response_json, dict):
        raise APIError(f"Invalid response JSON {response_json=} {type(response_json)=}")

    success = response_json.get("success", None)
    if success is not True:
        raise APIError(f"Flashlight API returned an error. Response: {response_json}")

    username = response_json.get("username", None)
    if not isinstance(username, str):
        raise APIError(f"Invalid username {username=} {type(username)=}")

    uuid = response_json.get("uuid", None)
    if not isinstance(uuid, str):
        raise APIError(f"Invalid uuid {uuid=} {type(uuid)=}")

    if not is_uuid(uuid):
        raise APIError(f"Invalid uuid format from flashlight {uuid=}")

    return Account(username=username, uuid=uuid)
