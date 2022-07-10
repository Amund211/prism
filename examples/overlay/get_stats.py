import functools
import logging
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from examples.overlay.player import KnownPlayer, NickedPlayer, PendingPlayer, Stats
from examples.overlay.player_cache import get_cached_player, set_cached_player
from prism.calc import bedwars_level_from_exp
from prism.minecraft import MojangAPIError, get_uuid
from prism.playerdata import (
    HypixelAPIError,
    HypixelAPIKeyError,
    HypixelAPIKeyHolder,
    MissingStatsError,
    get_gamemode_stats,
    get_player_data,
)
from prism.utils import div

logger = logging.getLogger(__name__)


def create_known_player(
    playerdata: dict[str, Any], username: str, uuid: str, nick: str | None = None
) -> KnownPlayer:
    try:
        bw_stats = get_gamemode_stats(playerdata, gamemode="Bedwars")
    except MissingStatsError:
        return KnownPlayer(
            username=username,
            nick=nick,
            uuid=uuid,
            stars=0,
            stats=Stats(
                fkdr=0,
                wlr=0,
                winstreak=0,
                winstreak_accurate=True,
            ),
        )

    winstreak = bw_stats.get("winstreak", None)
    return KnownPlayer(
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


def fetch_bedwars_stats(
    username: str,
    get_uuid: Callable[[str], str | None],
    get_player_data: Callable[[str], dict[str, Any] | None],
    denick: Callable[[str], str | None] = lambda nick: None,
) -> KnownPlayer | NickedPlayer:
    """Fetches the bedwars stats for the given player"""
    uuid = get_uuid(username)

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

    if uuid is None:
        # Could not find uuid or denick - assume nicked
        return NickedPlayer(nick=username)

    playerdata = get_player_data(uuid)

    logger.debug(
        f"Initial stats for {username} ({uuid}) {denicked=} {playerdata is None=}"
    )

    if not denicked and playerdata is None:
        # The username may be an existing minecraft account that has not
        # logged on to Hypixel. Then we would get a hit from Mojang, but
        # no hit from Hypixel and the username is still a nickname.
        denick_result = denick(username)
        if denick_result is not None:
            uuid = denick_result
            nick = username
            logger.debug(f"De-nicked {username} as {uuid} after hit from Mojang")
            playerdata = get_player_data(uuid)
            logger.debug(f"Stats for nicked {nick} ({uuid}) {playerdata is None=}")

    if playerdata is None:
        logger.debug("Got no playerdata - assuming player is nicked")
        return NickedPlayer(nick=username)

    if nick is not None:
        # Successfully de-nicked - update actual username
        username = playerdata["displayname"]
        logger.debug(f"De-nicked {nick} as {username}")

    return create_known_player(playerdata, username=username, uuid=uuid, nick=nick)


def get_uuid_from_mojang(username: str) -> str | None:  # pragma: nocover
    """Lookup uuid from Mojang"""
    try:
        return get_uuid(username)
    except MojangAPIError as e:
        logger.debug(f"Failed getting uuid for username {username} {e=}")
        return None


def get_player_data_from_hypixel(
    uuid: str,
    key_holder: HypixelAPIKeyHolder,
    on_request_completion: Callable[[bool], None],
) -> dict[str, Any] | None:  # pragma: nocover
    try:
        player_data = get_player_data(uuid, key_holder)
    except HypixelAPIError as e:
        logger.debug(f"Failed getting stats for {uuid=} {e=}")
        on_request_completion(False)
        return None
    except HypixelAPIKeyError as e:
        logger.debug(f"Invalid API key {e=}")
        on_request_completion(True)
        return None
    else:
        on_request_completion(False)
        return player_data


def get_bedwars_stats(
    username: str,
    key_holder: HypixelAPIKeyHolder,
    denick: Callable[[str], str | None] = lambda nick: None,
    on_request_completion: Callable[[bool], None] = lambda api_key_invalid: None,
) -> KnownPlayer | NickedPlayer:  # pragma: nocover
    """Get and caches the bedwars stats for the given player"""
    cached_stats = get_cached_player(username)

    if cached_stats is not None and not isinstance(cached_stats, PendingPlayer):
        logger.debug(f"Cache hit {username}")

        return cached_stats

    logger.debug(f"Cache miss {username}")

    player = fetch_bedwars_stats(
        username=username,
        get_uuid=get_uuid_from_mojang,
        get_player_data=functools.partial(
            get_player_data_from_hypixel,
            key_holder=key_holder,
            on_request_completion=on_request_completion,
        ),
        denick=denick,
    )

    if isinstance(player, KnownPlayer) and player.nick is not None:
        # If we look up by actual username, that means the user is not nicked
        set_cached_player(player.username, replace(player, nick=None))

    set_cached_player(username, player)

    return player
