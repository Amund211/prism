import logging
from dataclasses import replace
from typing import Iterable

from examples.overlay.controller import OverlayController
from examples.overlay.events import process_event
from examples.overlay.parsing import parse_logline
from examples.overlay.player import (
    KnownPlayer,
    NickedPlayer,
    PendingPlayer,
    create_known_player,
)

logger = logging.getLogger(__name__)


def set_nickname(
    *, username: str | None, nick: str, controller: OverlayController
) -> None:
    """Update the user's nickname"""
    logger.debug(f"Setting denick {nick=} => {username=}")

    old_nick = None

    if username is not None:
        uuid = controller.get_uuid(username)

        if uuid is None:
            logger.error(f"Failed getting uuid for '{username}' when setting nickname.")
            # Delete the entry for this nick
            old_nick = nick
    else:
        uuid = None
        # Delete the entry for this nick
        old_nick = nick

    with controller.settings.mutex:
        if uuid is not None and username is not None:
            # Search the known nicks in settings for the uuid
            for old_nick, nick_value in controller.settings.known_nicks.items():
                if uuid == nick_value["uuid"]:
                    new_nick_value = nick_value
                    break
            else:
                # Found no matching entries - make a new one
                new_nick_value = {"uuid": uuid, "comment": username}
                old_nick = None
        else:
            new_nick_value = None

        # Remove the old nick if found
        if old_nick is not None:
            controller.settings.known_nicks.pop(old_nick, None)

        if new_nick_value is not None:
            # Add your new nick
            controller.settings.known_nicks[nick] = new_nick_value

        controller.store_settings()

    with controller.nick_database.mutex:
        # Delete your old nick if found
        if old_nick is not None:
            controller.nick_database.default_database.pop(old_nick, None)

        if uuid is not None:
            # Add your new nick
            controller.nick_database.default_database[nick] = uuid

    if old_nick is not None:
        # Drop the stats cache for your old nick
        controller.player_cache.uncache_player(old_nick)

    # Drop the stats cache for your new nick so that we can fetch the stats
    controller.player_cache.uncache_player(nick)


def set_api_key(new_key: str, /, controller: OverlayController) -> None:
    """Update the API key that the download threads use"""
    controller.hypixel_api_key = new_key
    with controller.settings.mutex:
        controller.settings.hypixel_api_key = new_key
        controller.store_settings()

    # Clear the stats cache in case the old api key was invalid
    controller.player_cache.clear_cache()


def fetch_bedwars_stats(
    username: str, controller: OverlayController
) -> KnownPlayer | NickedPlayer:
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

    if uuid is None:
        # Could not find uuid or denick - assume nicked
        return NickedPlayer(nick=username)

    playerdata = controller.get_player_data(uuid)

    logger.debug(
        f"Initial stats for {username} ({uuid}) {denicked=} {playerdata is None=}"
    )

    if not denicked and playerdata is None:
        # The username may be an existing minecraft account that has not
        # logged on to Hypixel. Then we would get a hit from Mojang, but
        # no hit from Hypixel and the username is still a nickname.
        denick_result = denick(username, controller)
        if denick_result is not None:
            uuid = denick_result
            nick = username
            logger.debug(f"De-nicked {username} as {uuid} after hit from Mojang")
            playerdata = controller.get_player_data(uuid)
            logger.debug(f"Stats for nicked {nick} ({uuid}) {playerdata is None=}")

    if playerdata is None:
        logger.debug("Got no playerdata - assuming player is nicked")
        return NickedPlayer(nick=username)

    if nick is not None:
        # Successfully de-nicked - update actual username
        username = playerdata["displayname"]
        logger.debug(f"De-nicked {nick} as {username}")

    return create_known_player(playerdata, username=username, uuid=uuid, nick=nick)


def get_bedwars_stats(
    username: str,
    controller: OverlayController,
) -> KnownPlayer | NickedPlayer:
    """Get and caches the bedwars stats for the given player"""
    cached_stats = controller.player_cache.get_cached_player(username)

    if cached_stats is not None and not isinstance(cached_stats, PendingPlayer):
        logger.debug(f"Cache hit {username}")

        return cached_stats

    logger.debug(f"Cache miss {username}")

    player = fetch_bedwars_stats(username, controller)

    if isinstance(player, KnownPlayer) and player.nick is not None:
        # If we look up by actual username, that means the user is not nicked
        controller.player_cache.set_cached_player(
            player.username, replace(player, nick=None)
        )

    controller.player_cache.set_cached_player(username, player)

    return player


def denick(nick: str, controller: OverlayController) -> str | None:
    """Try denicking via the antisniper API, fallback to dict"""
    uuid = controller.nick_database.get_default(nick)

    # Return if the user has specified a denick
    if uuid is not None:
        logger.debug(f"Denicked with default database {nick} -> {uuid}")
        return uuid

    uuid = controller.denick(nick)

    if uuid is not None:
        logger.debug(f"Denicked with api {nick} -> {uuid}")
        return uuid

    uuid = controller.nick_database.get(nick)

    if uuid is not None:
        logger.debug(f"Denicked with database {nick} -> {uuid}")
        return uuid

    logger.debug(f"Failed denicking {nick}")

    return None


def fast_forward_state(controller: OverlayController, loglines: Iterable[str]) -> None:
    """Process the state changes for each logline without outputting anything"""
    for line in loglines:
        event = parse_logline(line)

        if event is None:
            continue

        process_event(controller, event)
