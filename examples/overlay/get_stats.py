import logging
import threading
from dataclasses import replace
from typing import Callable

from cachetools import TTLCache

from examples.overlay.player import (
    KnownPlayer,
    NickedPlayer,
    PendingPlayer,
    Player,
    Stats,
)
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

logger = logging.getLogger(__name__)

# Session stats cache
# Entries cached for 2mins, so they hopefully expire before the next queue
KNOWN_PLAYERS: TTLCache[str, Player] = TTLCache(maxsize=512, ttl=120)
STATS_MUTEX = threading.Lock()


def set_player_pending(username: str) -> PendingPlayer:
    """Note that the stats for this user are pending"""
    pending_player = PendingPlayer(username)

    with STATS_MUTEX:
        if username in KNOWN_PLAYERS:
            logger.error(f"Stats for {username} set to pending, but already exists")

        KNOWN_PLAYERS[username] = pending_player

    return pending_player


def get_cached_stats(username: str) -> Player | None:
    with STATS_MUTEX:
        return KNOWN_PLAYERS.get(username, None)


def update_cached_stats(
    username: str, update: Callable[[KnownPlayer], KnownPlayer]
) -> None:
    """Update the cached stats for a player"""
    with STATS_MUTEX:
        player = KNOWN_PLAYERS.get(username, None)
        if isinstance(player, KnownPlayer):
            KNOWN_PLAYERS[username] = update(player)
        else:
            logger.warning(f"Stats for {username} not found during update")


def uncache_stats(username: str) -> None:
    """Clear the cache entry for `username`"""
    with STATS_MUTEX:
        KNOWN_PLAYERS.pop(username, None)


def clear_cache() -> None:
    """Clear the entire stats cache"""
    with STATS_MUTEX:
        KNOWN_PLAYERS.clear()


def get_bedwars_stats(
    username: str,
    key_holder: HypixelAPIKeyHolder,
    denick: Callable[[str], str | None] = lambda nick: None,
) -> tuple[str | None, str | None, str | None, Player]:
    """
    Get the bedwars stats for the given player

    Returns username, nick, uuid, stats
    """
    cached_stats = get_cached_stats(username)

    if cached_stats is not None and not isinstance(cached_stats, PendingPlayer):
        logger.info(f"Cache hit {username}")
        if isinstance(cached_stats, NickedPlayer):
            return None, cached_stats.username, None, cached_stats
        elif isinstance(cached_stats, KnownPlayer):
            return (
                cached_stats.username,
                cached_stats.nick,
                cached_stats.uuid,
                cached_stats,
            )
        return False  # Unreachable - for typechecking

    logger.info(f"Cache miss {username}")

    # Lookup uuid from Mojang
    try:
        uuid = get_uuid(username)
    except MojangAPIError as e:
        # No match from Mojang -> assume the username is a nickname
        logger.debug(f"Failed getting uuid for username {username} {e=}")
        uuid = None

    # Look up in nick database if we got no match from Mojang
    nick: str | None = None
    denicked = False
    if uuid is None:
        denick_result = denick(username)
        if denick_result is not None:
            uuid = denick_result
            nick = username
            denicked = True
            logger.debug(f"De-nicked {username} as {uuid}")

    player: Player
    if uuid is None:
        player = NickedPlayer(nick=username)
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
            player = NickedPlayer(nick=username)
        else:
            if nick is not None:
                # Successfully de-nicked - update actual username
                username = playerdata["displayname"]
                logger.debug(f"Updating de-nicked {username=}")

            try:
                bw_stats = get_gamemode_stats(playerdata, gamemode="Bedwars")
            except MissingStatsError:
                player = KnownPlayer(
                    username=username,
                    uuid=uuid,
                    stars=0,
                    stats=Stats(
                        fkdr=0,
                        wlr=0,
                        winstreak=0,
                        winstreak_accurate=True,
                    ),
                )
            else:
                winstreak = bw_stats.get("winstreak", None)
                player = KnownPlayer(
                    username=username,
                    nick=nick,
                    uuid=uuid,
                    stars=bedwars_level_from_exp(bw_stats.get("Experience", 500)),
                    stats=Stats(
                        fkdr=div(
                            bw_stats.get("final_kills_bedwars", 0),
                            bw_stats.get("final_deaths_bedwars", 0),
                        ),
                        wlr=div(
                            bw_stats.get("wins_bedwars", 0),
                            bw_stats.get("games_played_bedwars", 0)
                            - bw_stats.get("wins_bedwars", 0),
                        ),
                        winstreak=winstreak,
                        winstreak_accurate=winstreak is not None,
                    ),
                )

    # Set the cache
    with STATS_MUTEX:
        if nick is None or isinstance(player, NickedPlayer):
            # Unnicked player or failed denicking
            KNOWN_PLAYERS[username] = player
        else:
            # Successful denicking
            KNOWN_PLAYERS[nick] = player
            # If we look up by original username, that means the user is not nicked
            KNOWN_PLAYERS[username] = replace(player, nick=None)

    return username, nick, uuid, player
