import functools
import logging
import queue

from prism.overlay.controller import ERROR_DURING_PROCESSING, OverlayController
from prism.overlay.get_stats import get_bedwars_stats
from prism.overlay.settings import SettingsDict
from prism.player import MISSING_WINSTREAKS, KnownPlayer, PendingPlayer, Player
from prism.uuid import compare_uuids

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
        if (
            uuid is not None
            and uuid is not ERROR_DURING_PROCESSING
            and username is not None
        ):
            # Search the known nicks in settings for the uuid
            for old_nick, nick_value in controller.settings.known_nicks.items():
                if compare_uuids(uuid, nick_value["uuid"]):
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

        controller.settings.flush_to_disk()

    with controller.nick_database.mutex:
        # Delete your old nick if found
        if old_nick is not None:
            controller.nick_database.default_database.pop(old_nick, None)

        if uuid is not None and uuid is not ERROR_DURING_PROCESSING:
            # Add your new nick
            controller.nick_database.default_database[nick] = uuid

    if old_nick is not None and old_nick != nick:
        # Drop the stats cache for your old nick
        controller.player_cache.uncache_player(old_nick)

    # Drop the stats cache for your new nick so that we can fetch the stats
    controller.player_cache.uncache_player(nick)

    controller.redraw_event.set()


def should_redraw(controller: OverlayController) -> bool:
    """Check if any updates happened since last time that needs a redraw"""
    # Check if the state update thread has issued any redraws since last time
    redraw = controller.redraw_event.is_set()

    # Check if any of the stats downloaded since last render are still in the lobby
    while True:
        try:
            username = controller.completed_stats_queue.get_nowait()
        except queue.Empty:
            break
        else:
            controller.completed_stats_queue.task_done()
            if username in controller.state.lobby_players:
                # We just received the stats of a player in the lobby
                # Redraw the screen in case the stats weren't there last time
                redraw = True

    if redraw:
        # We are going to redraw - clear any redraw request
        controller.redraw_event.clear()

    return redraw


def get_and_cache_player(
    username: str, completed_queue: queue.Queue[str], controller: OverlayController
) -> None:
    """Get a username from the requests queue and cache their stats"""
    # get_bedwars_stats sets the stats cache which will be read from later
    player = get_bedwars_stats(username, controller)

    # Tell the main thread that we downloaded this user's stats
    completed_queue.put(username)

    logger.debug(f"Finished gettings stats for {username}")

    # Get estimated winstreak if missing
    if isinstance(player, KnownPlayer) and player.is_missing_winstreaks:
        (
            estimated_winstreaks,
            winstreaks_accurate,
        ) = controller.get_estimated_winstreaks(player.uuid)

        if estimated_winstreaks is not MISSING_WINSTREAKS:
            logger.debug(f"Got estimated winstreak for {username}")
            for alias in player.aliases:
                controller.player_cache.update_cached_player(
                    alias,
                    functools.partial(
                        KnownPlayer.update_winstreaks,
                        **estimated_winstreaks,
                        winstreaks_accurate=winstreaks_accurate,
                    ),
                )

            # Tell the main thread that we got the estimated winstreak
            completed_queue.put(username)
            logger.debug(f"Updated missing winstreak for {username}")

    # Get tags
    if isinstance(player, KnownPlayer):
        tags = controller.get_tags(player.uuid)
        if tags is ERROR_DURING_PROCESSING:
            logger.error(f"Error getting tags for {username}")
        else:
            for alias in player.aliases:
                controller.player_cache.update_cached_player(
                    alias,
                    functools.partial(KnownPlayer.set_tags, tags=tags),
                )

            # Tell the main thread that we got the tags
            completed_queue.put(username)
            logger.debug(f"Set tags for {username}")


def update_settings(new_settings: SettingsDict, controller: OverlayController) -> None:
    """
    Update the settings from the settings dict, with required side-effects

    Caller must acquire lock on settings
    """
    logger.debug(f"Updating settings with {new_settings}")

    urchin_api_key_changed = (
        new_settings["urchin_api_key"] != controller.settings.urchin_api_key
    )

    # Known_nicks
    def uuid_changed(nickname: str) -> bool:
        """True if the uuid of the given nickname changed in new_settings"""
        return (
            new_settings["known_nicks"][nickname]
            != controller.settings.known_nicks[nickname]
        )

    new_nicknames = set(new_settings["known_nicks"].keys())
    old_nicknames = set(controller.settings.known_nicks.keys())

    added_nicknames = new_nicknames - old_nicknames
    removed_nicknames = old_nicknames - new_nicknames
    updated_nicknames = set(
        filter(uuid_changed, set.intersection(new_nicknames, old_nicknames))
    )

    # Update the Urchin API key
    if urchin_api_key_changed:
        controller.urchin_api_key_invalid = False

    # Refetch stats for nicknames that had a player assigned or unassigned
    # for nickname in added_nicknames + removed_nicknames:
    for nickname in set.union(added_nicknames, removed_nicknames):
        controller.player_cache.uncache_player(nickname)

    # Refetch stats for nicknames that were assigned to a different player
    for nickname in updated_nicknames:
        controller.player_cache.uncache_player(nickname)

    # Update default nick database
    # NOTE: Since the caller must acquire the settings lock, we have two locks here
    # Make sure that we always acquire the settings lock before the nick database lock
    # to avoid deadlocks
    with controller.nick_database.mutex:
        for nickname in removed_nicknames:
            controller.nick_database.default_database.pop(nickname, None)

        for nickname in set.union(added_nicknames, updated_nicknames):
            controller.nick_database.default_database[nickname] = new_settings[
                "known_nicks"
            ][nickname]["uuid"]

    discord_presence_settings_changed = (
        new_settings["discord_rich_presence"]
        != controller.settings.discord_rich_presence
        or new_settings["discord_show_username"]
        != controller.settings.discord_show_username
        or new_settings["discord_show_session_stats"]
        != controller.settings.discord_show_session_stats
        or new_settings["discord_show_party"] != controller.settings.discord_show_party
    )

    if discord_presence_settings_changed:
        controller.update_presence_event.set()

    # Redraw the overlay to reflect changes in the stats cache/nicknames
    controller.redraw_event.set()

    controller.settings.update_from(new_settings)

    controller.settings.flush_to_disk()


def autodenick_teammate(controller: OverlayController) -> None:
    """
    Automatically denick one teammate if possible

    If
        We are in queue
        The lobby is full and in sync
        *One* of our teammates is not in the lobby
        There is *one* unknown nick in the lobby (either not denicked or API denicked)
    We denick that nick to be our teammate
    """
    # Store a persistent view to the current state
    state = controller.state

    if not state.in_queue or state.out_of_sync:
        # We're not quite sure of the state of the lobby
        return

    # Teammates whose IGN is not present in the lobby
    # They could still be known to be in the lobby if we have already denicked them
    missing_teammates = set(state.party_members - state.lobby_players)

    if not missing_teammates:
        # Nothing to do
        return

    logger.info(f"Attempting to autodenick {missing_teammates=}")

    lobby_size = len(state.lobby_players)

    # Make sure the lobby is full, so that we know that all our teammates have joined
    # TODO: Make a better check that the lobby is full (e.g. 16/16)
    if lobby_size != 8 and lobby_size != 12 and lobby_size != 16:
        logger.info(f"Aborting autodenick due to non-full lobby {lobby_size=}")
        return

    if state.lobby_players != state.alive_players:
        logger.warning(
            "Aborting autodenick due to mismatch in lobby/alive, "
            f"lobby={state.lobby_players}, alive={state.alive_players}"
        )
        return

    # Use the cached stats to narrow missing_teammates and to find the unknown nick
    unknown_nick: str | None = None
    for player in state.lobby_players:
        # Use the long term cache, as the recency doesn't matter
        # We just want to know if they're an unknown nick or not
        stats = controller.player_cache.get_cached_player(player, long_term=True)

        if stats is None:
            logger.info(f"Aborting autodenick due to {player}'s stats missing")
            return
        elif isinstance(stats, PendingPlayer):
            logger.info(f"Aborting autodenick due to {player}'s stats being pending")
            return
        elif isinstance(stats, KnownPlayer):
            if stats.nick is None:
                # Known player is not denicked
                continue

            manual_denick_uuid = controller.nick_database.get_default(stats.nick)
            if manual_denick_uuid is not None and compare_uuids(
                manual_denick_uuid, stats.uuid
            ):
                # Manually denicked - trust the denick and mark the user as present
                missing_teammates -= {stats.username}

                if not missing_teammates:
                    logger.info("All teammates already denicked")
                    return

                continue

        # Player is either an unknown nick, or has been denicked by the API
        # Treat them as an unknown nick
        if unknown_nick is not None:
            logger.info(
                "Aborting autodenick due to multiple unknown nicks: "
                f"{unknown_nick}, {player} and possibly more."
            )
            return

        unknown_nick = player

    if unknown_nick is None:
        logger.info("Aborting autodenick due to no unknown nick in the lobby")
        return

    if len(missing_teammates) != 1:
        logger.info(f"Aborting autodenick due to multiple {missing_teammates=}")
        return

    # Unpack to get the one element
    (teammate,) = missing_teammates

    logger.info(f"Autodenicked teammate {unknown_nick} -> {teammate}")

    set_nickname(username=teammate, nick=unknown_nick, controller=controller)


def bedwars_game_ended(controller: OverlayController) -> None:
    """Clear the stats cache and set the game ended event"""
    controller.player_cache.clear_cache(short_term_only=True)
    controller.update_presence_event.set()


def get_cached_player_or_enqueue_request(
    controller: OverlayController, username: str, long_term: bool = False
) -> Player:
    """Get the player from the cache, or enqueue a request if not cached"""
    cached_stats = controller.player_cache.get_cached_player(
        username, long_term=long_term
    )

    if cached_stats is not None:
        # We have cached stats - return them
        return cached_stats

    # We don't have cached stats - enqueue a request and return a PendingPlayer
    # We set the player to pending to note that a request is in progress
    # NOTE: Set player to pending before requesting to prevent setting the player
    #       to pending after the request has been processed
    pending_stats = controller.player_cache.set_player_pending(username)
    logger.debug(f"Set player {username} to pending")
    controller.requested_stats_queue.put(username)

    return pending_stats
