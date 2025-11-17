import functools
import logging
from collections.abc import Callable
from json import JSONDecodeError

import requests
from requests.exceptions import RequestException, SSLError

from prism.errors import APIError, APIKeyError, APIThrottleError, PlayerNotFoundError
from prism.hypixel import create_known_player, get_playerdata_field
from prism.player import KnownPlayer
from prism.ratelimiting import RateLimiter
from prism.retry import ExecutionError, execute_with_retry
from prism.ssl_errors import MissingLocalIssuerSSLError, is_missing_local_issuer_error

logger = logging.getLogger(__name__)

STATS_ENDPOINT = "https://flashlight.prismoverlay.com/v1/playerdata"
WINSTREAK_ENDPOINT = "https://api.antisniper.net/v2/player/winstreak"

REQUEST_LIMIT, REQUEST_WINDOW = 360, 60  # Max requests per time window


def is_global_throttle_response(response: requests.Response) -> bool:  # pragma: nocover
    """
    Return True if the response is a 500: throttle

    This is a condition that can occur on the AntiSniper API
    """
    # We ignore the http status code

    try:
        response_json = response.json()
    except JSONDecodeError:
        return False

    if response_json.get("success", None) is not False:
        return False

    cause = response_json.get("cause", None)

    if not isinstance(cause, str) or "throttle" not in cause.lower():
        return False

    return True


def is_invalid_api_key_response(response: requests.Response) -> bool:  # pragma: nocover
    """Return True if the response is a 403: invalid api key"""
    if response.status_code != 403:
        return False

    try:
        response_json = response.json()
    except JSONDecodeError:
        return False

    if response_json.get("success", None) is not False:
        return False

    cause = response_json.get("cause", None)

    if not isinstance(cause, str) or "invalid api key" not in cause.lower():
        return False

    return True


def is_checked_too_many_offline_players_response(
    response: requests.Response,
) -> bool:  # pragma: nocover
    """Return True if the response is a 403: checked too many offline players"""
    if response.status_code != 403:
        return False

    try:
        response_json = response.json()
    except JSONDecodeError:
        return False

    if response_json.get("success", None) is not False:
        return False

    cause = response_json.get("cause", None)

    if not isinstance(cause, str) or "too many offline" not in cause.lower():
        return False

    return True


class StrangePlayerProvider:
    def __init__(
        self,
        *,
        session: requests.Session,
        retry_limit: int,
        initial_timeout: float,
        get_time_ns: Callable[[], int],
    ) -> None:
        self._retry_limit = retry_limit
        self._initial_timeout = initial_timeout
        self._get_time_ns = get_time_ns
        self._session = session
        self._limiter = RateLimiter(limit=120, window=60)

    @property
    def seconds_until_unblocked(self) -> float:
        """Return the number of seconds until we are unblocked"""
        return self._limiter.block_duration_seconds

    def _make_playerdata_request(
        self,
        *,
        url: str,
        user_id: str,
        last_try: bool,
    ) -> requests.Response:  # pragma: nocover
        try:
            # Uphold our prescribed rate-limits
            with self._limiter:
                response = self._session.get(url, headers={"X-User-Id": user_id})
        except SSLError as e:
            if is_missing_local_issuer_error(e):
                # Short circuit out of get_playerdata
                # NOTE: Remember to catch this exception in the caller
                raise MissingLocalIssuerSSLError(
                    "Request to Hypixel API failed due to missing local issuer cert"
                ) from e
            raise ExecutionError(
                "Request to Hypixel API failed due to an unknown SSL error"
            ) from e
        except RequestException as e:
            raise ExecutionError(
                "Request to AntiSniper API failed due to an unknown error"
            ) from e

        if is_checked_too_many_offline_players_response(response):
            raise ExecutionError(
                f"Checked too many offline players for {url}, retrying"
            )

        if response.status_code == 429 or response.status_code == 504 and not last_try:
            raise ExecutionError(
                "Request to AntiSniper API failed due to ratelimit, retrying"
            )

        return response

    def get_player(
        self,
        uuid: str,
        *,
        user_id: str,
    ) -> KnownPlayer:  # pragma: nocover
        """Get data about the given player from the /player API endpoint"""

        url = f"{STATS_ENDPOINT}?uuid={uuid}"

        try:
            response = execute_with_retry(
                functools.partial(
                    self._make_playerdata_request,
                    url=url,
                    user_id=user_id,
                ),
                retry_limit=self._retry_limit,
                initial_timeout=self._initial_timeout,
            )
        except ExecutionError as e:
            raise APIError(f"Request to Hypixel API failed for {uuid=}.") from e

        dataReceivedAtMs = self._get_time_ns() // 1_000_000

        if is_global_throttle_response(response) or response.status_code == 429:
            raise APIThrottleError(
                f"Request to Hypixel API failed with status code "
                f"{response.status_code}. Assumed due to API key throttle. "
                f"Response: {response.text}"
            )

        if is_invalid_api_key_response(response):
            raise APIKeyError(
                f"Request to Hypixel API failed with status code "
                f"{response.status_code}. Assumed invalid API key. "
                f"Response: {response.text}"
            )

        if is_checked_too_many_offline_players_response(response):
            raise APIError("Checked too many offline players for {uuid}")

        if response.status_code == 404:
            raise PlayerNotFoundError(f"Could not find a user with {uuid=} (404)")

        if not response:
            raise APIError(
                f"Request to Hypixel API failed with status code "
                f"{response.status_code} when getting data for player {uuid}. "
                f"Response: {response.text}"
            )

        try:
            response_json = response.json()
        except JSONDecodeError as e:
            raise APIError(
                "Failed parsing the response from the Hypixel API. "
                f"Raw content: {response.text}"
            ) from e

        if not response_json.get("success", False):
            raise APIError(f"Hypixel API returned an error. Response: {response_json}")

        playerdata = response_json.get("player", None)

        if playerdata is None:
            raise PlayerNotFoundError(f"Could not find a user with {uuid=}")

        if not isinstance(playerdata, dict):
            raise APIError(f"Invalid playerdata {playerdata=} {type(playerdata)=}")

        username = get_playerdata_field(
            playerdata, "displayname", str, "<missing name>"
        )

        return create_known_player(
            dataReceivedAtMs=dataReceivedAtMs,
            playerdata=playerdata,
            username=username,
            uuid=uuid,
        )
