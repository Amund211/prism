import logging
from dataclasses import dataclass
from typing import Callable, Literal, Union, overload

from hystatutils.calc import bedwars_level_from_exp
from hystatutils.playerdata import (
    HypixelAPIError,
    MissingStatsError,
    get_gamemode_stats,
    get_player_data,
)
from hystatutils.utils import div

StatName = Literal["stars", "fkdr", "wlr", "winstreak"]
InfoName = Literal["username"]
PropertyName = Literal[StatName, InfoName]

logger = logging.getLogger()

try:
    # Define a map username -> uuid so that we can look up by uuid instead of username
    from examples.customize import UUID_MAP
except ImportError:
    UUID_MAP: dict[str, str] = {}  # type: ignore[no-redef]


@dataclass(order=True)
class PlayerStats:
    """Dataclass holding the stats of a single player"""

    fkdr: float
    stars: float
    wlr: float
    winstreak: int
    username: str

    @property
    def nicked(self) -> bool:
        """Return True if the player is assumed to be nicked"""
        return False

    @overload
    def get_value(self, name: StatName) -> Union[int, float]:
        ...

    @overload
    def get_value(self, name: InfoName) -> str:
        ...

    def get_value(self, name: PropertyName) -> Union[str, int, float]:
        """Get the given stat from this player"""
        if name == "fkdr":
            return self.fkdr
        elif name == "stars":
            return self.stars
        elif name == "wlr":
            return self.wlr
        elif name == "winstreak":
            return self.winstreak
        elif name == "username":
            return self.username

    def get_string(self, name: PropertyName) -> str:
        """Get a string representation of the given stat"""
        value = self.get_value(name)
        if isinstance(value, int):
            return str(value)
        elif isinstance(value, str):
            return value
        elif isinstance(value, float):
            return f"{value:.2f}"
        else:
            raise ValueError(f"{name=} {value=}")


@dataclass(order=True)
class NickedPlayer:
    """Dataclass holding the stats of a single player assumed to be nicked"""

    username: str

    @property
    def nicked(self) -> bool:
        """Return True if the player is assumed to be nicked"""
        return True

    def get_value(self, name: PropertyName) -> Union[int, float]:
        """Get the given stat from this player (unknown in this case)"""
        return float("inf")

    def get_string(self, name: PropertyName) -> str:
        """Get a string representation of the given stat (unknown)"""
        if name == "username":
            return self.username

        return "unknown"


Stats = Union[PlayerStats, NickedPlayer]


# Cache per session
KNOWN_STATS: dict[str, Stats] = {}


def get_bedwars_stats(username: str, api_key: str) -> Stats:
    """Print a table of bedwars stats from the given player data"""
    global KNOWN_STATS

    cached_stats = KNOWN_STATS.get(username, None)
    if cached_stats is not None:
        logger.info(f"Cache hit {username}")
        return cached_stats

    logger.info(f"Cache miss {username}")

    stats: Stats

    try:
        playerdata = get_player_data(api_key, username, UUID_MAP=UUID_MAP)
    except HypixelAPIError as e:
        # Assume the players is a nick
        logger.info(f"Failed for {username}", e)
        stats = NickedPlayer(username=username)
    else:
        try:
            bw_stats = get_gamemode_stats(playerdata, gamemode="Bedwars")
        except MissingStatsError:
            stats = PlayerStats(username=username, stars=0, fkdr=0, wlr=0, winstreak=0)
        else:
            stats = PlayerStats(
                username=username,
                stars=bedwars_level_from_exp(bw_stats["Experience"]),
                fkdr=div(
                    bw_stats["final_kills_bedwars"],
                    bw_stats["final_deaths_bedwars"],
                ),
                wlr=div(
                    bw_stats["wins_bedwars"],
                    bw_stats["games_played_bedwars"] - bw_stats["wins_bedwars"],
                ),
                winstreak=bw_stats["winstreak"],
            )

    KNOWN_STATS[username] = stats

    return stats


RateStatsReturn = Union[tuple[bool, bool], tuple[bool, bool, Stats]]


def rate_stats_for_non_party_members(
    party_members: set[str],
) -> Callable[[Stats], RateStatsReturn]:
    def rate_stats(stats: Stats) -> RateStatsReturn:
        """Used as a key function for sorting"""
        is_teammate = stats.username not in party_members
        if stats.nicked:
            return (is_teammate, stats.nicked)

        return (is_teammate, stats.nicked, stats)

    return rate_stats
