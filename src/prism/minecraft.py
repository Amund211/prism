import threading
from json import JSONDecodeError
from typing import cast

import requests
from requests.exceptions import RequestException

from prism.ratelimiting import RateLimiter

USERPROFILES_ENDPOINT = "https://api.mojang.com/users/profiles/minecraft"
REQUEST_LIMIT, REQUEST_WINDOW = 100, 60  # Max requests per time window


class MojangAPIError(ValueError):
    """Exception raised when we receive an error from the Mojang api"""

    pass


# Be nice to the Mojang api :)
limiter = RateLimiter(limit=REQUEST_LIMIT, window=REQUEST_WINDOW)

# TODO: implement a disk cache
# TTL on this cache can be large because for a username to get a new uuid the user
# must first change their ign, then, after 37 days, someone else can get the name
LOWERCASE_UUID_CACHE: dict[str, str] = {}  # Mapping username.lower() -> uuid
UUID_MUTEX = threading.Lock()


def get_uuid(username: str) -> str | None:
    """Get the uuid of all the user. None if not found."""
    with UUID_MUTEX:
        cache_hit = LOWERCASE_UUID_CACHE.get(username.lower(), None)

    if cache_hit is not None:
        return cache_hit

    try:
        # Uphold our prescribed rate-limits
        with limiter:
            response = requests.get(f"{USERPROFILES_ENDPOINT}/{username}")
    except RequestException as e:
        raise MojangAPIError(
            f"Request to Mojang API failed due to a connection error {e}"
        ) from e

    if not response:
        raise MojangAPIError(
            f"Request to Mojang API failed with status code {response.status_code}. "
            f"Response: {response.text}"
        )

    if response.status_code != 200:
        return None

    try:
        response_json = response.json()
    except JSONDecodeError:
        raise MojangAPIError(
            "Failed parsing the response from the Mojang API. "
            f"Raw content: {response.text}"
        )

    # reponse is {"id": "...", "name": "..."}
    uuid = response_json["id"]

    # Set cache
    with UUID_MUTEX:
        LOWERCASE_UUID_CACHE[username.lower()] = uuid

    return cast(str, uuid)
