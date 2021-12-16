import time
from collections import deque
from datetime import datetime
from json import JSONDecodeError
from typing import Optional, cast

import requests

USERPROFILES_ENDPOINT = "https://api.mojang.com/users/profiles/minecraft"
REQUEST_LIMIT, REQUEST_WINDOW = 100, 60  # Max requests per time window


class MojangAPIError(ValueError):
    """Exception raised when we receive an error from the Mojang api"""

    pass


# Be nice to the Mojang api :)
made_requests = deque([datetime.now()], maxlen=REQUEST_LIMIT)

# TODO: implement a disk cache
LOWERCASE_USERNAME_UUID: dict[str, str] = {}


def get_uuid(username: str) -> Optional[str]:
    """Get the uuid of all the user. None if not found."""
    if username.lower() in LOWERCASE_USERNAME_UUID:
        return LOWERCASE_USERNAME_UUID[username.lower()]

    now = datetime.now()
    if len(made_requests) == REQUEST_LIMIT:
        timespan = now - made_requests[0]
        if timespan.total_seconds() < REQUEST_WINDOW:
            time.sleep(REQUEST_WINDOW - timespan.total_seconds())

    made_requests.append(now)

    response = requests.get(f"{USERPROFILES_ENDPOINT}/{username}")

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
    LOWERCASE_USERNAME_UUID[username.lower()] = uuid

    return cast(str, uuid)
