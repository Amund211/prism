import functools
import logging
import threading
from collections.abc import Mapping
from enum import Enum, auto
from json import JSONDecodeError

import requests
from cachetools import TTLCache
from requests.exceptions import RequestException

from prism.overlay.player import MISSING_WINSTREAKS, GamemodeName, Winstreaks
from prism.ratelimiting import RateLimiter
from prism.requests import make_prism_requests_session
from prism.retry import ExecutionError, execute_with_retry

logger = logging.getLogger(__name__)

DENICK_ENDPOINT = "https://api.antisniper.net/v2/other/denick"
WINSTREAK_ENDPOINT = "https://api.antisniper.net/v2/player/winstreak"

REQUEST_LIMIT, REQUEST_WINDOW = 360, 60  # Max requests per time window


class Flag(Enum):
    NOT_SET = auto()  # Singleton for cache misses


# Cache both successful and failed denicks for 60 mins
LOWERCASE_DENICK_CACHE = TTLCache[str, str | None](maxsize=1024, ttl=60 * 60)
DENICK_MUTEX = threading.Lock()

# Use a connection pool for the requests
SESSION = make_prism_requests_session()


def set_denick_cache(nick: str, uuid: str | None) -> str | None:
    """Set the cache entry for nick, and return the uuid"""
    with DENICK_MUTEX:
        LOWERCASE_DENICK_CACHE[nick.lower()] = uuid

    return uuid


def get_denick_cache(nick: str) -> str | None | Flag:
    """Get the cache entry for nick"""
    with DENICK_MUTEX:
        return LOWERCASE_DENICK_CACHE.get(nick.lower(), Flag.NOT_SET)


class AntiSniperAPIKeyHolder:
    """Class associating an api key with a RateLimiter instance"""

    def __init__(
        self, key: str, limit: int = REQUEST_LIMIT, window: float = REQUEST_WINDOW
    ):
        self.key = key
        self.limiter = RateLimiter(limit=limit, window=window)


def _make_request(
    *, url: str, key_holder: AntiSniperAPIKeyHolder, last_try: bool
) -> requests.Response:  # pragma: nocover
    try:
        # Uphold our prescribed rate-limits
        with key_holder.limiter:
            response = SESSION.get(url)
    except RequestException as e:
        raise ExecutionError(
            "Request to AntiSniper API failed due to an unknown error"
        ) from e

    if response.status_code == 429 and not last_try:
        raise ExecutionError(
            "Request to AntiSniper API failed due to ratelimit, retrying"
        )

    return response


def denick(
    nick: str, key_holder: AntiSniperAPIKeyHolder
) -> str | None:  # pragma: nocover
    """
    Get data about the given nick from the v2 denick API endpoint

    https://api.antisniper.net/#tag/Other/paths/~1v2~1other~1denick/get
    """

    cache_hit = get_denick_cache(nick)

    # If cache hits and was not a failure, return it
    if cache_hit is not Flag.NOT_SET and cache_hit is not None:
        return cache_hit

    try:
        response = execute_with_retry(
            functools.partial(
                _make_request,
                url=f"{DENICK_ENDPOINT}?key={key_holder.key}&nick={nick}",
                key_holder=key_holder,
            ),
            retry_limit=3,
            timeout=5,
        )
    except ExecutionError:
        logger.exception("Request to denick endpoint reached max retries")
        return set_denick_cache(nick, None)

    if not response:
        logger.error(
            f"Request to denick endpoint failed with status code {response.status_code}"
            f" when getting name for nick {nick}. Response: {response.text}"
        )
        return set_denick_cache(nick, None)

    try:
        response_json = response.json()
    except JSONDecodeError:
        logger.error(
            "Failed parsing the response from the denick endpoint. "
            f"Raw content: {response.text}"
        )
        return set_denick_cache(nick, None)

    return set_denick_cache(nick, parse_denick_response(response_json))


def parse_denick_response(response_json: Mapping[str, object]) -> str | None:
    """Parse the response from the denick endpoint"""
    if not response_json.get("success", False):
        logger.error(f"Denick endpoint returned an error. Response: {response_json}")
        return None

    results = response_json.get("results", None)

    if not isinstance(results, list):
        logger.error(
            f"Got wrong return type for results from denick endpoint {results}"
        )
        return None

    if not results:
        logger.debug("Denick results list empty")
        return None

    chosen_result = results[0]

    if not isinstance(chosen_result, dict):
        logger.error(
            f"Got wrong type for chosen result from denick results {chosen_result}"
        )
        return None

    uuid = chosen_result.get("uuid", None)

    if not isinstance(uuid, str):
        logger.error(f"Got wrong return type for uuid from denick endpoint {uuid}")
        return None

    return uuid


def get_estimated_winstreaks(
    uuid: str, key_holder: AntiSniperAPIKeyHolder
) -> tuple[Winstreaks, bool]:  # pragma: nocover
    """
    Get the estimated winstreaks of the given uuid

    https://api.antisniper.net/#tag/Player/paths/~1v2~1player~1winstreak/get
    """
    try:
        response = execute_with_retry(
            functools.partial(
                _make_request,
                url=f"{WINSTREAK_ENDPOINT}?key={key_holder.key}&player={uuid}",
                key_holder=key_holder,
            ),
            retry_limit=3,
            timeout=5,
        )
    except ExecutionError:
        logger.exception("Request to winstreaks endpoint reached max retries")
        return MISSING_WINSTREAKS, False

    if not response:
        logger.error(
            f"Request to winstreak endpoint failed with status code "
            f"{response.status_code} for {uuid=}. Response: {response.text}"
        )
        return MISSING_WINSTREAKS, False

    try:
        response_json = response.json()
    except JSONDecodeError:
        logger.error(
            "Failed parsing the response from the winstreak endpoint. "
            f"Raw content: {response.text}"
        )
        return MISSING_WINSTREAKS, False

    return parse_estimated_winstreaks_response(response_json)


def parse_estimated_winstreaks_response(
    response_json: Mapping[str, object]
) -> tuple[Winstreaks, bool]:
    """Parse the reponse from the winstreaks endpoint"""
    if not response_json.get("success", False):
        logger.error(f"Winstreak endpoint returned an error. Response: {response_json}")
        return MISSING_WINSTREAKS, False

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
