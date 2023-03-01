import logging
from dataclasses import replace
from typing import Iterable

from prism.overlay.behaviour import (
    autodenick_teammate,
    set_hypixel_api_key,
    set_nickname,
)
from prism.overlay.controller import OverlayController
from prism.overlay.events import Event, EventType
from prism.overlay.parsing import parse_logline
from prism.overlay.state import OverlayState

logger = logging.getLogger(__name__)


def process_event(
    controller: OverlayController, event: Event
) -> tuple[OverlayState, bool]:
    """Return an updated OverlayState, and a boolean flag redraw"""
    # Store a persistent view to the current state
    state = controller.state

    if event.event_type is EventType.INITIALIZE_AS:
        # Initializing means the player restarted/switched accounts -> clear the state
        logger.info(f"Playing as {state.own_username}. Cleared party and lobby.")

        new_state = replace(
            state, own_username=event.username, in_queue=False, out_of_sync=False
        )
        return new_state.clear_party().clear_lobby(), True

    if event.event_type is EventType.NEW_NICKNAME:
        # User got a new nickname
        logger.info(f"Setting new nickname {event.nick}={state.own_username}")
        if state.own_username is None:
            logger.warning(
                "Own username is not set, could not add denick entry for {event.nick}."
            )
            return state, False

        set_nickname(
            username=state.own_username, nick=event.nick, controller=controller
        )

        # set_nickname sets redraw_flag
        return state, False

    if event.event_type is EventType.LOBBY_SWAP:
        # Changed lobby -> clear the lobby
        logger.info("Received lobby swap. Clearing the lobby")
        return state.clear_lobby().leave_queue(), True

    if event.event_type is EventType.LOBBY_LIST:
        # Results from /who -> override lobby_players
        logger.info(
            f"Updating lobby players from who command: '{', '.join(event.usernames)}'"
        )

        # TODO: This is the correct logic for when we do /who in queue, but not in game.
        #       /who in game returns only the list of alive players.
        new_state = replace(state, out_of_sync=False)
        return new_state.join_queue().set_lobby(event.usernames), True

    if event.event_type is EventType.LOBBY_JOIN:
        if event.player_cap < 8:
            logger.debug("Gamemode has too few players to be bedwars. Skipping.")
            return state, False

        new_state = state.join_queue().add_to_lobby(event.username)

        if event.player_count != len(new_state.lobby_players):
            # We are out of sync with the lobby.
            # This happens when you first join a lobby, as the previous lobby is
            # never cleared. It could also be due to a bug.
            logger.debug("Player count out of sync.")
            out_of_sync = True

            if event.player_count < len(new_state.lobby_players):
                # We know of too many players, some must actually not be in the lobby
                logger.debug("Too many players in lobby. Clearing.")
                new_state = new_state.clear_lobby().add_to_lobby(event.username)

                # Clearing the lobby may have gotten us back in sync
                out_of_sync = event.player_count != len(new_state.lobby_players)
        else:
            # We are in sync now
            out_of_sync = False

        logger.info(
            f"{event.username} joined your lobby "
            f"({event.player_count}/{event.player_cap})"
        )

        return replace(new_state, out_of_sync=out_of_sync), True

    if event.event_type is EventType.LOBBY_LEAVE:
        # Someone left the lobby -> Remove them from the lobby
        logger.info(f"{event.username} left your lobby")

        return state.remove_from_lobby(event.username), True

    if event.event_type is EventType.PARTY_DETACH:
        # Leaving the party -> remove all but yourself from the party
        logger.info("Leaving the party, clearing all members")

        return state.clear_party(), True

    if event.event_type is EventType.PARTY_ATTACH:
        # You joined a player's party -> add them to your party

        logger.info(f"Joined {event.username}'s party")

        # Make sure the party is clean to start with
        return state.clear_party().add_to_party(event.username), True

    if event.event_type is EventType.PARTY_JOIN:
        # Someone joined your party -> add them to your party
        new_state = state
        for username in event.usernames:
            new_state = new_state.add_to_party(username)

        logger.info(f"{' ,'.join(event.usernames)} joined your party")

        return new_state, True

    if event.event_type is EventType.PARTY_LEAVE:
        if state.own_username in event.usernames:
            # You left the party -> clear the party instead
            return state.clear_party(), True

        new_state = state

        # Someone left your party -> remove them from your party
        for username in event.usernames:
            new_state = new_state.remove_from_party(username)

        logger.info(f"{' ,'.join(event.usernames)} left your party")

        return new_state, True

    if event.event_type is EventType.PARTY_LIST_INCOMING:
        # This is a response from /pl (/party list)
        # In the following lines we will get all the party members -> clear the party

        logger.debug(
            "Receiving response from /pl -> clearing party and awaiting further data"
        )

        # No need to redraw as we're waiting for further input
        return state.clear_party(), False

    if event.event_type is EventType.PARTY_ROLE_LIST:
        logger.info(f"Adding party {event.role} {', '.join(event.usernames)} from /pl")

        new_state = state
        for username in event.usernames:
            new_state = new_state.add_to_party(username)

        return new_state, True

    if event.event_type is EventType.START_BEDWARS_GAME:
        # Bedwars game has started
        logger.info("Bedwars game starting")

        # Try to denick a teammate right before we leave the queue (start the game)
        autodenick_teammate(controller)

        return state.leave_queue(), False

    if event.event_type is EventType.BEDWARS_FINAL_KILL:
        # Bedwars final kill
        logger.info(f"Final kill: {event.dead_player} - {event.raw_message}")

        return state.mark_dead(event.dead_player), True

    if event.event_type is EventType.END_BEDWARS_GAME:
        # Bedwars game has ended
        logger.info("Bedwars game ended")

        return state.clear_lobby(), True

    if event.event_type is EventType.NEW_API_KEY:
        # User got a new API key
        logger.info("Setting new API key")

        # NOTE: Make sure not to deadlock
        set_hypixel_api_key(event.key, controller)

        # set_hypixel_api_key sets redraw_flag
        return state, False

    if event.event_type is EventType.WHISPER_COMMAND_SET_NICK:
        # User set a nick with /w !nick=username
        logger.info(f"Setting nick from whisper command {event.nick}={event.username}")

        # NOTE: Make sure not to deadlock
        set_nickname(username=event.username, nick=event.nick, controller=controller)

        # set_nickname sets redraw_flag
        return state, False


def fast_forward_state(controller: OverlayController, loglines: Iterable[str]) -> None:
    """
    Process the state changes for each logline without outputting anything

    Caller must ensure exclusive write-access to controller.state
    """
    logger.info("Fast forwarding state")
    for line in loglines:
        event = parse_logline(line)

        if event is None:
            continue

        controller.state, redraw = process_event(controller, event)
    logger.info("Done fast forwarding state")


def process_loglines(loglines: Iterable[str], controller: OverlayController) -> None:
    """Update state and set the redraw event"""
    for line in loglines:
        event = parse_logline(line)

        if event is None:
            continue

        with controller.state_mutex:  # Exclusive write-access
            controller.state, redraw = process_event(controller, event)

        if redraw:
            # Tell the main thread we need a redraw
            controller.redraw_event.set()
