import logging
import threading
from json import JSONDecodeError
from typing import Optional

import requests
from cachetools import TTLCache
from requests.exceptions import RequestException

from prism.ratelimiting import RateLimiter

logger = logging.getLogger(__name__)

DENICK_ENDPOINT = "http://api.antisniper.net/denick"
ANTISNIPER_ENDPOINT = "http://api.antisniper.net/antisniper"
REQUEST_LIMIT, REQUEST_WINDOW = 100, 60  # Max requests per time window


# Cache both successful and failed denicks for 60 mins
DENICK_CACHE: TTLCache[str, Optional[str]] = TTLCache(maxsize=1024, ttl=60 * 60)
DENICK_MUTEX = threading.Lock()


def set_denick_cache(nick: str, uuid: Optional[str]) -> Optional[str]:
    """Set the cache entry for nick, and return the uuid"""
    with DENICK_MUTEX:
        DENICK_CACHE[nick] = uuid

    return uuid


class AntiSniperAPIKeyHolder:
    """Class associating an api key with a RateLimiter instance"""

    def __init__(
        self, key: str, limit: int = REQUEST_LIMIT, window: float = REQUEST_WINDOW
    ):
        self.key = key
        self.limiter = RateLimiter(limit=limit, window=window)


def denick(nick: str, key_holder: AntiSniperAPIKeyHolder) -> Optional[str]:
    """Get data about the given nick from the /denick API endpoint"""
    try:
        # Uphold our prescribed rate-limits
        with key_holder.limiter:
            response = requests.get(
                f"{DENICK_ENDPOINT}?key={key_holder.key}&nick={nick}"
            )
    except RequestException as e:
        logger.error(f"Request to denick endpoint failed due to a connection error {e}")
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

    if not response_json.get("success", False):
        logger.error(f"Denick endpoint returned an error. Response: {response_json}")
        return set_denick_cache(nick, None)

    playerdata = response_json.get("player", None)

    if not isinstance(playerdata, dict):
        logger.error(
            f"Got wrong return type for playerdata from denick endpoint {playerdata}"
        )
        return set_denick_cache(nick, None)

    uuid = playerdata.get("uuid", None)

    if not isinstance(uuid, str):
        logger.error(f"Got wrong return type for uuid from denick endpoint {uuid}")
        return set_denick_cache(nick, None)

    return set_denick_cache(nick, uuid)


def queue_data(name: str, key_holder: AntiSniperAPIKeyHolder) -> Optional[int]:
    """Get queue data about the given username/nick from the /antisniper API endpoint"""
    try:
        # Uphold our prescribed rate-limits
        with key_holder.limiter:
            response = requests.get(
                f"{ANTISNIPER_ENDPOINT}?key={key_holder.key}&name={name}"
            )
    except RequestException as e:
        logger.error(
            f"Request to antisniper endpoint failed due to a connection error {e}"
        )
        return None

    if not response:
        logger.error(
            f"Request to antisniper endpoint failed with status code "
            f"{response.status_code} when getting queue data for name {name}. "
            f"Response: {response.text}"
        )
        return None

    try:
        response_json = response.json()
    except JSONDecodeError:
        logger.error(
            "Failed parsing the response from the antisniper endpoint. "
            f"Raw content: {response.text}"
        )
        return None

    if not response_json.get("success", False):
        logger.error(
            f"Antisniper endpoint returned an error. Response: {response_json}"
        )
        return None

    data = response_json.get("data", None)

    if not isinstance(data, dict):
        logger.error(f"Got wrong return type for data from antisniper endpoint {data}")
        return None

    queue_data = response_json.get(name, None)

    if not isinstance(queue_data, dict):
        logger.error(
            "Got wrong return type for queue data from antisniper endpoint: "
            f"'{queue_data}'"
        )
        return None

    queues = queue_data.get("queues", None)

    if not isinstance(queues, dict):
        logger.error(
            f"Got wrong return type for queues from antisniper endpoint {queues}"
        )
        return None

    last_3_min = queues.get("last_3_min", None)

    if not isinstance(last_3_min, int):
        logger.error(
            "Got wrong return type for last_3_min from antisniper endpoint "
            f"{last_3_min}"
        )
        return None

    return last_3_min
