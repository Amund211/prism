import time
from collections import defaultdict, deque
from datetime import datetime
from json import JSONDecodeError
from typing import Any, cast

import requests


class MissingStatsError(ValueError):
    """Exception raised when the player has no stats for the gamemode"""

    pass


class HypixelAPIError(ValueError):
    """Exception raised when the player is not found"""

    pass


GamemodeData = dict[str, Any]
PlayerData = dict[str, Any]

PLAYER_ENDPOINT = "https://api.hypixel.net/player"
REQUEST_LIMIT = 100  # Max requests per minute


# Initing with now is semantically wrong, because it implies we just made a request
# but it is a bit safer
made_requests = deque([datetime.now()], maxlen=REQUEST_LIMIT)


def get_player_data(
    api_key: str, identifier: str, uuid: bool = False, UUID_MAP: dict[str, str] = {}
) -> PlayerData:
    """Get data about the given player from the /player API endpoint"""
    if not uuid and identifier.lower() in UUID_MAP:
        identifier = UUID_MAP[identifier.lower()]
        uuid = True

    identifier_type = "uuid" if uuid else "name"

    now = datetime.now()
    if len(made_requests) == REQUEST_LIMIT:
        timespan = now - made_requests[0]
        if timespan.total_seconds() < 60:
            time.sleep(60 - timespan.total_seconds())

    made_requests.append(now)

    response = requests.get(
        f"{PLAYER_ENDPOINT}?key={api_key}&{identifier_type}={identifier}"
    )

    if not response:
        raise HypixelAPIError(
            f"Request to Hypixel API failed with status code {response.status_code} "
            f"when getting data for player {identifier}. Response: {response.text}"
        )

    try:
        response_json = response.json()
    except JSONDecodeError:
        raise HypixelAPIError(
            "Failed parsing the response from the Hypixel API. "
            f"Raw content: {response.text}"
        )

    if not response_json.get("success", False):
        raise HypixelAPIError(
            f"Hypixel API returned an error. Response: {response_json}"
        )

    playerdata = response_json["player"]

    if not playerdata:
        raise HypixelAPIError(
            f"Could not find a user with {identifier_type} {identifier}"
        )

    return cast(PlayerData, playerdata)  # TODO: properly type response


def get_gamemode_stats(playerdata: PlayerData, gamemode: str) -> GamemodeData:
    """Return the stats of the player in the given gamemode"""
    if gamemode not in playerdata["stats"]:
        raise MissingStatsError(
            f"{playerdata['displayname']} is missing stats in {gamemode.lower()}"
        )

    # Any stat defaults to 0 if not present
    return defaultdict(int, playerdata["stats"][gamemode])
