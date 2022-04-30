import logging
import threading
from dataclasses import dataclass, field, replace
from typing import Callable, Literal, Optional, Union, overload

from cachetools import TTLCache

from prism.calc import bedwars_level_from_exp
from prism.minecraft import MojangAPIError, get_uuid
from prism.playerdata import (
    HypixelAPIError,
    HypixelAPIKeyHolder,
    MissingStatsError,
    get_gamemode_stats,
    get_player_data,
)
from prism.utils import div

StatName = Literal["stars", "fkdr", "wlr", "winstreak"]
InfoName = Literal["username"]
PropertyName = Literal[StatName, InfoName]

logger = logging.getLogger(__name__)


@dataclass(order=True, frozen=True)
class PlayerStats:
    """Dataclass holding the stats of a single player"""

    fkdr: float
    stars: float
    wlr: float
    winstreak: int
    username: str
    nick: Optional[str] = field(default=None, compare=False)

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
            return self.username + (f" ({self.nick})" if self.nick is not None else "")

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


@dataclass(order=True, frozen=True)
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


@dataclass(order=True, frozen=True)
class PendingPlayer:
    """Dataclass holding the stats of a single player whose stats are pending"""

    username: str

    @property
    def nicked(self) -> bool:
        """Return True if the player is assumed to be nicked"""
        return False

    def get_value(self, name: PropertyName) -> Union[int, float]:
        """Get the given stat from this player (unknown in this case)"""
        return float("-inf")

    def get_string(self, name: PropertyName) -> str:
        """Get a string representation of the given stat (unknown)"""
        if name == "username":
            return self.username

        return "-"


Stats = Union[PlayerStats, NickedPlayer, PendingPlayer]


# Session stats cache
# Entries cached for 2mins, so they hopefully expire before the next queue
KNOWN_STATS: TTLCache[str, Stats] = TTLCache(maxsize=512, ttl=120)
STATS_MUTEX = threading.Lock()


def set_player_pending(username: str) -> PendingPlayer:
    """Note that the stats for this user are pending"""
    pending_player = PendingPlayer(username)

    with STATS_MUTEX:
        if username in KNOWN_STATS:
            logger.error(f"Stats for {username} set to pending, but already exists")

        KNOWN_STATS[username] = pending_player

    return pending_player


def get_cached_stats(username: str) -> Optional[Stats]:
    with STATS_MUTEX:
        return KNOWN_STATS.get(username, None)


def uncache_stats(username: str) -> None:
    """Clear the cache entry for `username`"""
    with STATS_MUTEX:
        KNOWN_STATS.pop(username, None)


def clear_cache() -> None:
    """Clear the entire stats cache"""
    with STATS_MUTEX:
        KNOWN_STATS.clear()


def get_bedwars_stats(
    username: str,
    key_holder: HypixelAPIKeyHolder,
    denick: Callable[[str], Optional[str]] = lambda nick: None,
) -> Stats:
    """Get the bedwars stats for the given player"""
    cached_stats = get_cached_stats(username)

    if cached_stats is not None and not isinstance(cached_stats, PendingPlayer):
        logger.info(f"Cache hit {username}")
        return cached_stats

    logger.info(f"Cache miss {username}")

    # Lookup uuid from Mojang
    try:
        uuid = get_uuid(username)
    except MojangAPIError as e:
        # No match from Mojang -> assume the username is a nickname
        logger.debug(f"Failed getting uuid for username {username} {e=}")
        uuid = None

    # Look up in nick database if we got no match from Mojang
    nick: Optional[str] = None
    denicked = False
    if uuid is None:
        denick_result = denick(username)
        if denick_result is not None:
            uuid = denick_result
            nick = username
            denicked = True
            logger.debug(f"De-nicked {username} as {uuid}")

    stats: Stats
    if uuid is None:
        stats = NickedPlayer(username=username)
    else:
        try:
            playerdata = get_player_data(uuid, key_holder)
        except HypixelAPIError as e:
            logger.debug(
                f"Failed initially getting stats for {username} ({uuid}) {denicked=} "
                f"{e=}"
            )
            playerdata = None

        if not denicked and playerdata is None:
            denick_result = denick(username)
            if denick_result is not None:
                # The username may be an existing minecraft account that has not
                # logged on to Hypixel. Then we would get a hit from Mojang, but
                # no hit from Hypixel and the username is still a nickname.
                uuid = denick_result
                nick = username
                logger.debug(f"De-nicked {username} as {uuid} after hit from Mojang")
                try:
                    playerdata = get_player_data(uuid, key_holder)
                except HypixelAPIError as e:
                    logger.debug(
                        f"Failed getting stats for nicked {nick} ({uuid}) {e=}"
                    )
                    playerdata = None

        if playerdata is None:
            logger.debug("Got no playerdata - assuming player is nicked")
            stats = NickedPlayer(username=username)
        else:
            if nick is not None:
                # Successfully de-nicked - update actual username
                username = playerdata["displayname"]
                logger.debug(f"Updating de-nicked {username=}")

            try:
                bw_stats = get_gamemode_stats(playerdata, gamemode="Bedwars")
            except MissingStatsError:
                stats = PlayerStats(
                    username=username, stars=0, fkdr=0, wlr=0, winstreak=0
                )
            else:
                stats = PlayerStats(
                    username=username,
                    nick=nick,
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

    # Set the cache
    with STATS_MUTEX:
        if nick is None or isinstance(stats, NickedPlayer):
            # Unnicked player or failed denicking
            KNOWN_STATS[username] = stats
        else:
            # Successful denicking
            KNOWN_STATS[nick] = stats
            # If we look up by original username, that means the user is not nicked
            KNOWN_STATS[username] = replace(stats, nick=None)

    return stats


RateStatsReturn = tuple[bool, bool, Stats]


def rate_stats_for_non_party_members(
    party_members: set[str],
) -> Callable[[Stats], RateStatsReturn]:
    def rate_stats(stats: Stats) -> RateStatsReturn:
        """Used as a key function for sorting"""
        is_enemy = stats.username not in party_members
        if not isinstance(stats, PlayerStats):
            # Hack to compare other Stats instances by username only
            placeholder_stats = PlayerStats(
                fkdr=0, stars=0, wlr=0, winstreak=0, username=stats.username
            )
            return (is_enemy, stats.nicked, placeholder_stats)

        return (is_enemy, stats.nicked, stats)

    return rate_stats


def sort_stats(stats: list[Stats], party_members: set[str]) -> list[Stats]:
    """Sort the stats based on fkdr. Order party members last"""
    return list(
        sorted(
            stats,
            key=rate_stats_for_non_party_members(party_members),
            reverse=True,
        )
    )
