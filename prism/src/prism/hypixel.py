import functools
from collections.abc import Mapping
from json import JSONDecodeError
from typing import TypeVar

import requests
from requests.exceptions import RequestException

from prism.calc import bedwars_level_from_exp
from prism.errors import (
    APIError,
    APIKeyError,
    APIThrottleError,
    PlayerNotFoundError,
)
from prism.player import KnownPlayer, Stats
from prism.ratelimiting import RateLimiter
from prism.requests import make_prism_requests_session
from prism.retry import ExecutionError, execute_with_retry
from prism.utils import div

PLAYER_ENDPOINT = "https://api.hypixel.net/player"
REQUEST_LIMIT, REQUEST_WINDOW = 60, 60  # Max requests per time window

# Use a connection pool for the requests
SESSION = make_prism_requests_session()


class MissingBedwarsStatsError(ValueError):
    """Exception raised when the player has no stats in bedwars"""


class HypixelAPIKeyHolder:
    """Class associating an api key with a RateLimiter instance"""

    def __init__(
        self, key: str, limit: int = REQUEST_LIMIT, window: float = REQUEST_WINDOW
    ):
        self.key = key
        # Be nice to the Hypixel api :)
        self.limiter = RateLimiter(limit=limit, window=window)


def _make_request(
    *, uuid: str, key_holder: HypixelAPIKeyHolder, last_try: bool
) -> requests.Response:  # pragma: nocover
    try:
        # Uphold our prescribed rate-limits
        with key_holder.limiter:
            response = SESSION.get(
                f"{PLAYER_ENDPOINT}?key={key_holder.key}&uuid={uuid}"
            )
    except RequestException as e:
        raise ExecutionError(
            "Request to Hypixel API failed due to an unknown error"
        ) from e

    if response.status_code == 429 and not last_try:
        raise ExecutionError("Request to Hypixel API failed due to ratelimit, retrying")

    return response


def get_player_data(
    uuid: str,
    key_holder: HypixelAPIKeyHolder,
    retry_limit: int = 5,
    initial_timeout: float = 2,
) -> Mapping[str, object]:  # pragma: nocover
    """Get data about the given player from the /player API endpoint"""

    try:
        response = execute_with_retry(
            functools.partial(_make_request, uuid=uuid, key_holder=key_holder),
            retry_limit=retry_limit,
            initial_timeout=initial_timeout,
        )
    except ExecutionError as e:
        raise APIError(f"Request to Hypixel API failed for {uuid=}.") from e

    if response.status_code == 404:
        raise PlayerNotFoundError(f"Could not find a user with {uuid=} (404)")

    if response.status_code == 403:
        raise APIKeyError(
            f"Request to Hypixel API failed with status code {response.status_code}. "
            f"Assumed invalid API key. Response: {response.text}"
        )

    if response.status_code == 429:
        raise APIThrottleError(
            f"Request to Hypixel API failed with status code {response.status_code}. "
            f"Assumed due to API key throttle. Response: {response.text}"
        )

    if not response:
        raise APIError(
            f"Request to Hypixel API failed with status code {response.status_code} "
            f"when getting data for player {uuid}. Response: {response.text}"
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


def get_gamemode_stats(
    playerdata: Mapping[str, object], gamemode: str
) -> Mapping[str, object]:
    """Return the stats of the player in the given gamemode"""
    stats = playerdata.get("stats", None)
    name = playerdata.get("displayname", "<missing name>")

    if not isinstance(stats, dict):
        raise MissingBedwarsStatsError(f"{name} is missing stats in all gamemodes")

    gamemode_data = stats.get(gamemode, None)

    if not isinstance(gamemode_data, dict):
        raise MissingBedwarsStatsError(f"{name} is missing stats in {gamemode.lower()}")

    return gamemode_data


PlayerDataField = TypeVar("PlayerDataField")
DefaultType = TypeVar("DefaultType")


def get_playerdata_field(
    playerdata: Mapping[str, object],
    field: str,
    data_type: type[PlayerDataField],
    default: DefaultType,
) -> PlayerDataField | DefaultType:
    """Get a field from the playerdata, fallback if missing or wrong type"""
    value = playerdata.get(field, None)
    if isinstance(value, data_type):
        return value
    return default


def create_known_player(
    dataReceivedAtMs: int,
    playerdata: Mapping[str, object],
    username: str,
    uuid: str,
    nick: str | None = None,
) -> KnownPlayer:
    lastLoginMs = get_playerdata_field(playerdata, "lastLogin", int, None)
    lastLogoutMs = get_playerdata_field(playerdata, "lastLogout", int, None)

    try:
        bw_stats = get_gamemode_stats(playerdata, gamemode="Bedwars")
    except MissingBedwarsStatsError:
        return KnownPlayer(
            dataReceivedAtMs=dataReceivedAtMs,
            username=username,
            nick=nick,
            uuid=uuid,
            lastLoginMs=lastLoginMs,
            lastLogoutMs=lastLogoutMs,
            stars=0,
            stats=Stats(
                index=0,
                fkdr=0,
                kdr=0,
                bblr=0,
                wlr=0,
                winstreak=0,
                winstreak_accurate=True,
                kills=0,
                finals=0,
                beds=0,
                wins=0,
            ),
        )

    winstreak = get_playerdata_field(bw_stats, "winstreak", int, None)
    stars = bedwars_level_from_exp(
        get_playerdata_field(bw_stats, "Experience", int, 500)
    )
    kills = get_playerdata_field(bw_stats, "kills_bedwars", int, 0)
    finals = get_playerdata_field(bw_stats, "final_kills_bedwars", int, 0)
    beds = get_playerdata_field(bw_stats, "beds_broken_bedwars", int, 0)
    wins = get_playerdata_field(bw_stats, "wins_bedwars", int, 0)

    if winstreak is None and wins == 0:
        # The winstreak field is not populated until your first win
        # If you have no wins we know you don't have a winstreak
        winstreak = 0

    fkdr = div(finals, get_playerdata_field(bw_stats, "final_deaths_bedwars", int, 0))
    return KnownPlayer(
        dataReceivedAtMs=dataReceivedAtMs,
        username=username,
        nick=nick,
        uuid=uuid,
        stars=stars,
        lastLoginMs=lastLoginMs,
        lastLogoutMs=lastLogoutMs,
        stats=Stats(
            index=stars * fkdr**2,
            fkdr=fkdr,
            kdr=div(kills, get_playerdata_field(bw_stats, "deaths_bedwars", int, 0)),
            bblr=div(beds, get_playerdata_field(bw_stats, "beds_lost_bedwars", int, 0)),
            wlr=div(wins, get_playerdata_field(bw_stats, "losses_bedwars", int, 0)),
            winstreak=winstreak,
            winstreak_accurate=winstreak is not None,
            kills=kills,
            finals=finals,
            beds=beds,
            wins=wins,
        ),
    )
