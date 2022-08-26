import logging
from typing import Iterable

from examples.overlay.controller import OverlayController
from examples.overlay.parsing import parse_logline
from examples.overlay.process_event import process_event

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


def set_hypixel_api_key(new_key: str, /, controller: OverlayController) -> None:
    """Update the API key that the download threads use"""
    controller.set_hypixel_api_key(new_key)
    controller.api_key_invalid = False

    with controller.settings.mutex:
        controller.settings.hypixel_api_key = new_key
        controller.store_settings()

    # Clear the stats cache in case the old api key was invalid
    controller.player_cache.clear_cache()


def fast_forward_state(controller: OverlayController, loglines: Iterable[str]) -> None:
    """Process the state changes for each logline without outputting anything"""
    for line in loglines:
        event = parse_logline(line)

        if event is None:
            continue

        process_event(controller, event)
