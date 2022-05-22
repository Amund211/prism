from json import JSONDecodeError
from typing import Any, cast

import requests
from requests.exceptions import RequestException

from prism.ratelimiting import RateLimiter

GamemodeData = dict[str, Any]
PlayerData = dict[str, Any]

PLAYER_ENDPOINT = "https://api.hypixel.net/player"
REQUEST_LIMIT, REQUEST_WINDOW = 100, 60  # Max requests per time window


class HypixelAPIKeyHolder:
    """Class associating an api key with a RateLimiter instance"""

    def __init__(
        self, key: str, limit: int = REQUEST_LIMIT, window: float = REQUEST_WINDOW
    ):
        self.key = key
        # Be nice to the Hypixel api :)
        self.limiter = RateLimiter(limit=limit, window=window)


class MissingStatsError(ValueError):
    """Exception raised when the player has no stats for the gamemode"""

    pass


class HypixelAPIError(ValueError):
    """Exception raised when the player is not found"""

    pass


def get_player_data(uuid: str, key_holder: HypixelAPIKeyHolder) -> PlayerData:
    """Get data about the given player from the /player API endpoint"""
    try:
        # Uphold our prescribed rate-limits
        with key_holder.limiter:
            response = requests.get(
                f"{PLAYER_ENDPOINT}?key={key_holder.key}&uuid={uuid}"
            )
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
    stats = playerdata.get("stats", None)
    if not isinstance(stats, dict):
        raise MissingStatsError(
            f"{playerdata['displayname']} is missing stats in all gamemodes"
        )

    gamemode_data = stats.get(gamemode, None)

    if not isinstance(gamemode_data, dict):
        raise MissingStatsError(
            f"{playerdata['displayname']} is missing stats in {gamemode.lower()}"
        )

    return gamemode_data
