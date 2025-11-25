import logging
from dataclasses import replace

from prism.overlay.controller import ERROR_DURING_PROCESSING, OverlayController
from prism.player import KnownPlayer, NickedPlayer, UnknownPlayer

logger = logging.getLogger(__name__)


def denick(nick: str, controller: OverlayController) -> str | None:
    """Try denicking via the nick database"""
    uuid = controller.nick_database.get_default(nick)

    # Return if the user has specified a denick
    if uuid is not None:
        logger.debug(f"Denicked with default database {nick} -> {uuid}")
        return uuid

    uuid = controller.nick_database.get(nick)

    if uuid is not None:
        logger.debug(f"Denicked with database {nick} -> {uuid}")
        return uuid

    logger.debug(f"Failed denicking {nick}")

    return None


def fetch_bedwars_stats(
    username: str, controller: OverlayController
) -> KnownPlayer | NickedPlayer | UnknownPlayer:
    """Fetches the bedwars stats for the given player"""
    uuid = controller.get_uuid(username)
    if uuid is ERROR_DURING_PROCESSING:
        # Error while getting uuid -> unknown player
        logger.warning(
            f"Error while getting uuid for '{username}' - returning UnknownPlayer"
        )
        return UnknownPlayer(username)

    # Look up in nick database if we got no match from Mojang
    nick: str | None = None
    denicked = False
    if uuid is None:
        denick_result = denick(username, controller)
        if denick_result is not None:
            uuid = denick_result
            nick = username
            denicked = True
            logger.debug(f"De-nicked {username} as {uuid}")

    if uuid is None:
        # Could not find uuid or denick - assume nicked
        return NickedPlayer(nick=username)

    player = controller.get_player(uuid)
    if player is ERROR_DURING_PROCESSING:
        logger.warning(
            f"Error while getting player for '{uuid}' - returning UnknownPlayer"
        )
        return UnknownPlayer(username)

    logger.debug(f"Initial stats for {username} ({uuid}) {denicked=} {player is None=}")

    if (
        not denicked
        and player is not None
        and player.username.lower() != username.lower()
    ):
        # We got a hit from Mojang for the username, but querying Hypixel we got a
        # different name - assume that the player is outdated and that the player
        # is actually nicked. Try denicking.
        logger.error(
            f"Mismatching player name for {username=} {uuid=} {player.username=}. "
            "Assuming the player is nicked and attempting denick."
        )
        player = None

    if not denicked and player is None:
        # The username may be an existing minecraft account that has not
        # logged on to Hypixel. Then we would get a hit from Mojang, but
        # no hit from Hypixel and the username is still a nickname.
        denick_result = denick(username, controller)
        if denick_result is not None:
            uuid = denick_result
            nick = username
            logger.debug(f"De-nicked {username} as {uuid} after hit from Mojang")

            player = controller.get_player(uuid)
            if player is ERROR_DURING_PROCESSING:  # pragma: no cover
                logger.warning(
                    f"Error while getting player for '{uuid}' - returning UnknownPlayer"
                )
                return UnknownPlayer(username)

            logger.debug(f"Stats for nicked {nick} ({uuid}) {player is None=}")

    if player is None:
        logger.debug("Got no player - assuming player is nicked")
        return NickedPlayer(nick=username)

    if nick is not None:
        # Successfully de-nicked - update the KnownPlayer with nick information
        # Also update the username from the displayname if needed
        logger.debug(f"De-nicked {nick} as {player.username}")
        player = replace(player, nick=nick)

    return player


def get_and_cache_stats(
    username: str,
    controller: OverlayController,
) -> KnownPlayer | NickedPlayer | UnknownPlayer:
    """Get and cache the bedwars stats for the given player"""
    # NOTE: We store the genus before we make the request
    #       If the cache gets cleared between now and when the request finished,
    #       the genus will be incremented and this stats instance will not be cached.
    #       The stats instance will still be returned.
    cache_genus = controller.player_cache.current_genus

    player = fetch_bedwars_stats(username, controller)

    if isinstance(player, KnownPlayer) and player.nick is not None:
        # If we look up by actual username, that means the user is not nicked
        controller.player_cache.set_cached_player(
            player.username, replace(player, nick=None), cache_genus
        )

    controller.player_cache.set_cached_player(username, player, cache_genus)

    return player
