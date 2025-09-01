import functools
import logging
from collections.abc import Mapping
from json import JSONDecodeError

import requests
from requests.exceptions import RequestException, SSLError

from prism import VERSION_STRING
from prism.errors import APIError, APIKeyError, APIThrottleError, PlayerNotFoundError
from prism.player import MISSING_WINSTREAKS, GamemodeName, Winstreaks
from prism.ratelimiting import RateLimiter
from prism.requests import make_prism_requests_session
from prism.retry import ExecutionError, execute_with_retry
from prism.ssl_errors import MissingLocalIssuerSSLError, is_missing_local_issuer_error

logger = logging.getLogger(__name__)

STATS_ENDPOINT = "https://flashlight.recdep.no"
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


class AntiSniperAPIKeyHolder:
    """Class associating an api key with a RateLimiter instance"""

    def __init__(
        self, key: str, limit: int = REQUEST_LIMIT, window: float = REQUEST_WINDOW
    ):
        self.key = key
        self.limiter = RateLimiter(limit=limit, window=window)


class StrangePlayerProvider:
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

    def get_playerdata_for_uuid(
        self,
        uuid: str,
        *,
        user_id: str,
    ) -> Mapping[str, object]:  # pragma: nocover
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

        return playerdata


class AntiSniperWinstreakProvider:
    def __init__(
        self,
        *,
        retry_limit: int,
        initial_timeout: float,
    ) -> None:
        self._retry_limit = retry_limit
        self._initial_timeout = initial_timeout

        self._session = make_prism_requests_session()
        self._session.headers.update({"Reason": f"Prism overlay {VERSION_STRING}"})

        self._limiter = RateLimiter(limit=360, window=60)

    @property
    def seconds_until_unblocked(self) -> float:
        """Return the number of seconds until we are unblocked"""
        return self._limiter.block_duration_seconds

    def get_estimated_winstreaks_for_uuid(
        self, uuid: str, *, antisniper_api_key: str
    ) -> tuple[Winstreaks, bool]:  # pragma: nocover
        """
        Get the estimated winstreaks of the given uuid

        https://api.antisniper.net/#tag/Player/paths/~1v2~1player~1winstreak/get
        """
        try:
            response = execute_with_retry(
                functools.partial(
                    self._make_request,
                    url=(
                        f"{WINSTREAK_ENDPOINT}?key={antisniper_api_key}"
                        f"&player={uuid}"
                    ),
                    limiter=self._limiter,
                ),
                retry_limit=self._retry_limit,
                initial_timeout=self._initial_timeout,
            )
        except ExecutionError:
            logger.exception("Request to winstreaks endpoint reached max retries")
            return MISSING_WINSTREAKS, False

        if response.status_code == 403:
            raise APIKeyError(
                f"Request to Antisniper API failed with status code "
                f"{response.status_code}. Assumed invalid API key. "
                f"Response: {response.text}"
            )

        if is_global_throttle_response(response) or response.status_code == 429:
            raise APIThrottleError(
                f"Request to AntiSniper API failed with status code "
                f"{response.status_code}. Assumed due to API key throttle. "
                f"Response: {response.text}"
            )

        if not response:
            logger.error(
                f"Request to winstreak endpoint failed with status code "
                f"{response.status_code} for {uuid=}. Response: {response.text}"
            )
            raise APIError(
                f"Request to Antisniper API failed with status code "
                f"{response.status_code} when getting winstreaks for player {uuid}. "
                f"Response: {response.text}"
            )

        try:
            response_json = response.json()
        except JSONDecodeError:
            logger.error(
                "Failed parsing the response from the winstreak endpoint. "
                f"Raw content: {response.text}"
            )
            raise APIError("Failed parsing the response from the winstreak endpoint. ")

        return parse_estimated_winstreaks_response(response_json)

    def _make_request(
        self, *, url: str, limiter: RateLimiter, last_try: bool
    ) -> requests.Response:  # pragma: nocover
        try:
            # Uphold our prescribed rate-limits
            with limiter:
                response = self._session.get(url)
        except RequestException as e:
            raise ExecutionError(
                "Request to AntiSniper API failed due to an unknown error"
            ) from e

        if is_checked_too_many_offline_players_response(response):
            raise ExecutionError(
                f"Checked too many offline players for {url}, retrying"
            )

        throttled = is_global_throttle_response(response) or response.status_code == 429
        if throttled and not last_try:
            raise ExecutionError(
                "Request to AntiSniper API failed due to ratelimit, retrying"
            )

        return response


def parse_estimated_winstreaks_response(
    response_json: Mapping[str, object],
) -> tuple[Winstreaks, bool]:
    """Parse the reponse from the winstreaks endpoint"""
    if not response_json.get("success", False):
        logger.error(f"Winstreak endpoint returned an error. Response: {response_json}")
        raise APIError("Winstreak endpoint returned an error.")

    # Getting the winstreaks
    winstreaks: dict[GamemodeName, int | None] = {}

    DATA_NAMES: dict[GamemodeName, str] = {
        "overall": "overall",
        "solo": "eight_one",
        "doubles": "eight_two",
        "threes": "four_three",
        "fours": "four_four",
    }

    for gamemode, data_name in DATA_NAMES.items():
        winstreak = response_json.get(f"{data_name}_winstreak", None)
        if winstreak is not None and not isinstance(winstreak, int):
            logger.error(f"Got wrong return type for {gamemode} winstreak {winstreak=}")
            winstreak = None

        winstreaks[gamemode] = winstreak

    return (
        Winstreaks(
            overall=winstreaks["overall"],
            solo=winstreaks["solo"],
            doubles=winstreaks["doubles"],
            threes=winstreaks["threes"],
            fours=winstreaks["fours"],
        ),
        False,  # Don't trust winstreak estimates from antisniper
    )
