from collections import defaultdict
from json import JSONDecodeError
from typing import Any, cast

import requests
from requests.exceptions import RequestException

from hystatutils.ratelimiting import RateLimiter


class MissingStatsError(ValueError):
    """Exception raised when the player has no stats for the gamemode"""

    pass


class HypixelAPIError(ValueError):
    """Exception raised when the player is not found"""

    pass


GamemodeData = dict[str, Any]
PlayerData = dict[str, Any]

PLAYER_ENDPOINT = "https://api.hypixel.net/player"
REQUEST_LIMIT, REQUEST_WINDOW = 100, 60  # Max requests per time window

# Be nice to the Hypixel api :)
limiter = RateLimiter(limit=REQUEST_LIMIT, window=REQUEST_WINDOW)


def get_player_data(api_key: str, uuid: str) -> PlayerData:
    """Get data about the given player from the /player API endpoint"""
    # Uphold our prescribed rate-limits
    limiter.wait()

    try:
        response = requests.get(f"{PLAYER_ENDPOINT}?key={api_key}&uuid={uuid}")
    except RequestException as e:
        raise HypixelAPIError(
            f"Request to Hypixel API failed due to a connection error {e}"
        ) from e

    if not response:
        raise HypixelAPIError(
            f"Request to Hypixel API failed with status code {response.status_code} "
            f"when getting data for player {uuid}. Response: {response.text}"
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
        raise HypixelAPIError(f"Could not find a user with uuid {uuid}")

    return cast(PlayerData, playerdata)  # TODO: properly type response


def get_gamemode_stats(playerdata: PlayerData, gamemode: str) -> GamemodeData:
    """Return the stats of the player in the given gamemode"""
    if "stats" not in playerdata:
        raise MissingStatsError(
            f"{playerdata['displayname']} is missing stats in all gamemodes"
        )

    if gamemode not in playerdata["stats"]:
        raise MissingStatsError(
            f"{playerdata['displayname']} is missing stats in {gamemode.lower()}"
        )

    # Any stat defaults to 0 if not present
    return defaultdict(int, playerdata["stats"][gamemode])
