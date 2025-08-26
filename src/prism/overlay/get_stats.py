import logging
from dataclasses import replace

from prism.hypixel import create_known_player, get_playerdata_field
from prism.overlay.real_controller import ERROR_DURING_PROCESSING, OverlayController
from prism.player import KnownPlayer, NickedPlayer, PendingPlayer, UnknownPlayer

logger = logging.getLogger(__name__)


def denick(nick: str, controller: OverlayController) -> str | None:
    """Try denicking via the antisniper API, fallback to dict"""
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

    if uuid is ERROR_DURING_PROCESSING:
        # Error while getting uuid -> unknown player
        logger.warning(
            f"Error while getting uuid for '{username}' - returning UnknownPlayer"
        )
        return UnknownPlayer(username)

    if uuid is None:
        # Could not find uuid or denick - assume nicked
        return NickedPlayer(nick=username)

    dataReceivedAtMs, playerdata = controller.get_playerdata(uuid)

    logger.debug(
        f"Initial stats for {username} ({uuid}) {denicked=} {playerdata is None=}"
    )

    if (
        not denicked
        and playerdata is not None
        and playerdata is not ERROR_DURING_PROCESSING
    ):
        # We think the player is not nicked, and have found their stats
        displayname = get_playerdata_field(
            playerdata, "displayname", str, "<missing name>"
        )

        if displayname.lower() != username.lower():
            # ... but their displayname is incorrect - assume that the playerdata is
            # outdated and that the player is actually nicked. Try denicking.
            logger.error(
                f"Mismatching displayname for {username=} {uuid=} {displayname=}. "
                "Assuming the player is nicked and attempting denick."
            )
            playerdata = None

    if (
        not denicked
        and playerdata is None
        and playerdata is not ERROR_DURING_PROCESSING
    ):
        # The username may be an existing minecraft account that has not
        # logged on to Hypixel. Then we would get a hit from Mojang, but
        # no hit from Hypixel and the username is still a nickname.
        denick_result = denick(username, controller)
        if denick_result is not None:
            uuid = denick_result
            nick = username
            logger.debug(f"De-nicked {username} as {uuid} after hit from Mojang")
            dataReceivedAtMs, playerdata = controller.get_playerdata(uuid)
            logger.debug(f"Stats for nicked {nick} ({uuid}) {playerdata is None=}")

    if playerdata is ERROR_DURING_PROCESSING:
        logger.warning(
            f"Error while getting uuid for '{username}' - returning UnknownPlayer"
        )
        return UnknownPlayer(username)

    if playerdata is None:
        logger.debug("Got no playerdata - assuming player is nicked")
        return NickedPlayer(nick=username)

    if nick is not None:
        # Successfully de-nicked - update actual username
        username = get_playerdata_field(
            playerdata, "displayname", str, "<missing name>"
        )
        logger.debug(f"De-nicked {nick} as {username}")

    return create_known_player(
        dataReceivedAtMs, playerdata, username=username, uuid=uuid, nick=nick
    )


def get_bedwars_stats(
    username: str,
    controller: OverlayController,
) -> KnownPlayer | NickedPlayer | UnknownPlayer:
    """Get and cache the bedwars stats for the given player"""
    cached_stats = controller.player_cache.get_cached_player(username)

    if cached_stats is not None and not isinstance(cached_stats, PendingPlayer):
        logger.debug(f"Cache hit {username}")

        return cached_stats

    logger.debug(f"Cache miss {username}")

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
