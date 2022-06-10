import logging
from dataclasses import replace
from typing import Callable

from examples.overlay.player import (
    KnownPlayer,
    NickedPlayer,
    PendingPlayer,
    Player,
    Stats,
)
from examples.overlay.player_cache import get_cached_player, set_cached_player
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


def fetch_bedwars_stats(
    username: str,
    key_holder: HypixelAPIKeyHolder,
    denick: Callable[[str], str | None] = lambda nick: None,
) -> KnownPlayer | NickedPlayer:  # pragma: nocover
    """Fetches the bedwars stats for the given player"""
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

    return player


def get_bedwars_stats(
    username: str,
    key_holder: HypixelAPIKeyHolder,
    denick: Callable[[str], str | None] = lambda nick: None,
) -> KnownPlayer | NickedPlayer:  # pragma: nocover
    """Get and caches the bedwars stats for the given player"""
    cached_stats = get_cached_player(username)

    if cached_stats is not None and not isinstance(cached_stats, PendingPlayer):
        logger.debug(f"Cache hit {username}")

        return cached_stats

    logger.debug(f"Cache miss {username}")

    player = fetch_bedwars_stats(
        username=username, key_holder=key_holder, denick=denick
    )

    # Set the cache
    if isinstance(player, KnownPlayer) and player.nick is not None:
        set_cached_player(player.nick, player)
        # If we look up by original username, that means the user is not nicked
        set_cached_player(username, replace(player, nick=None))
    else:
        set_cached_player(username, player)

    return player
