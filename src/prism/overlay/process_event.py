import logging
from typing import Iterable

from prism.overlay.behaviour import set_hypixel_api_key, set_nickname
from prism.overlay.controller import OverlayController
from prism.overlay.events import Event, EventType
from prism.overlay.parsing import parse_logline

logger = logging.getLogger(__name__)


def process_event(controller: OverlayController, event: Event) -> bool:
    """Update the state based on the event, return True if a redraw is desired"""
    state = controller.state

    if event.event_type is EventType.INITIALIZE_AS:
        # Initializing means the player restarted/switched accounts -> clear the state
        state.own_username = event.username
        state.clear_party()
        state.clear_lobby()

        logger.info(f"Playing as {state.own_username}. Cleared party and lobby.")
        return True

    if event.event_type is EventType.NEW_NICKNAME:
        # User got a new nickname
        logger.info(f"Setting new nickname {event.nick}={state.own_username}")
        if state.own_username is None:
            logger.warning(
                "Own username is not set, could not add denick entry for {event.nick}."
            )
            return False

        set_nickname(
            username=state.own_username, nick=event.nick, controller=controller
        )

        # We should redraw so that we can properly denick ourself
        return True

    if event.event_type is EventType.LOBBY_SWAP:
        # Changed lobby -> clear the lobby
        logger.info("Received lobby swap. Clearing the lobby")
        state.clear_lobby()
        state.leave_queue()

        return True

    if event.event_type is EventType.LOBBY_LIST:
        # Results from /who -> override lobby_players
        logger.info(
            f"Updating lobby players from who command: '{', '.join(event.usernames)}'"
        )
        # TODO: This is the correct logic for when we do /who in queue, but not in game.
        #       /who in game returns only the list of alive players.
        state.out_of_sync = False
        state.join_queue()
        state.set_lobby(event.usernames)

        return True

    if event.event_type is EventType.LOBBY_JOIN:
        if event.player_cap < 8:
            logger.debug("Gamemode has too few players to be bedwars. Skipping.")
            return False

        state.join_queue()
        state.add_to_lobby(event.username)

        if event.player_count != len(state.lobby_players):
            # We are out of sync with the lobby.
            # This happens when you first join a lobby, as the previous lobby is
            # never cleared. It could also be due to a bug.
            logger.debug("Player count out of sync.")
            out_of_sync = True

            if event.player_count < len(state.lobby_players):
                # We know of too many players, some must actually not be in the lobby
                logger.debug("Too many players in lobby. Clearing.")
                state.clear_lobby()
                state.add_to_lobby(event.username)

                # Clearing the lobby may have gotten us back in sync
                out_of_sync = event.player_count != len(state.lobby_players)

            state.out_of_sync = out_of_sync
        else:
            # We are in sync now
            state.out_of_sync = False

        logger.info(
            f"{event.username} joined your lobby "
            f"({event.player_count}/{event.player_cap})"
        )

        return True

    if event.event_type is EventType.LOBBY_LEAVE:
        # Someone left the lobby -> Remove them from the lobby
        state.remove_from_lobby(event.username)

        logger.info(f"{event.username} left your lobby")

        return True

    if event.event_type is EventType.PARTY_DETACH:
        # Leaving the party -> remove all but yourself from the party
        logger.info("Leaving the party, clearing all members")

        state.clear_party()

        return True

    if event.event_type is EventType.PARTY_ATTACH:
        # You joined a player's party -> add them to your party
        state.clear_party()  # Make sure the party is clean to start with
        state.add_to_party(event.username)

        logger.info(f"Joined {event.username}'s party")

        return True

    if event.event_type is EventType.PARTY_JOIN:
        # Someone joined your party -> add them to your party
        for username in event.usernames:
            state.add_to_party(username)

        logger.info(f"{' ,'.join(event.usernames)} joined your party")

        return True

    if event.event_type is EventType.PARTY_LEAVE:
        if state.own_username in event.usernames:
            # You left the party -> clear the party instead
            state.clear_party()
            return True

        # Someone left your party -> remove them from your party
        for username in event.usernames:
            state.remove_from_party(username)

        logger.info(f"{' ,'.join(event.usernames)} left your party")

        return True

    if event.event_type is EventType.PARTY_LIST_INCOMING:
        # This is a response from /pl (/party list)
        # In the following lines we will get all the party members -> clear the party

        logger.debug(
            "Receiving response from /pl -> clearing party and awaiting further data"
        )

        state.clear_party()

        return False  # No need to redraw as we're waiting for further input

    if event.event_type is EventType.PARTY_ROLE_LIST:
        logger.info(f"Adding party {event.role} {', '.join(event.usernames)} from /pl")

        for username in event.usernames:
            state.add_to_party(username)

        return True

    if event.event_type is EventType.START_BEDWARS_GAME:
        # Bedwars game has started
        logger.info("Bedwars game starting")
        state.leave_queue()

        return False

    if event.event_type is EventType.BEDWARS_FINAL_KILL:
        # Bedwars final kill
        logger.info(f"Final kill: {event.dead_player} - {event.raw_message}")
        state.mark_dead(event.dead_player)

        return True

    if event.event_type is EventType.END_BEDWARS_GAME:
        # Bedwars game has ended
        logger.info("Bedwars game ended")
        state.clear_lobby()

        return True

    if event.event_type is EventType.NEW_API_KEY:
        # User got a new API key
        logger.info("Setting new API key")
        set_hypixel_api_key(event.key, controller)

        return True

    if event.event_type is EventType.WHISPER_COMMAND_SET_NICK:
        # User set a nick with /w !nick=username
        logger.info(f"Setting nick from whisper command {event.nick}={event.username}")
        set_nickname(username=event.username, nick=event.nick, controller=controller)
        return True


def fast_forward_state(controller: OverlayController, loglines: Iterable[str]) -> None:
    """Process the state changes for each logline without outputting anything"""
    logger.info("Fast forwarding state")
    for line in loglines:
        event = parse_logline(line)

        if event is None:
            continue

        process_event(controller, event)
    logger.info("Done fast forwarding state")


def process_loglines(loglines: Iterable[str], controller: OverlayController) -> None:
    """Update state and set the redraw event"""
    for line in loglines:
        event = parse_logline(line)

        if event is None:
            continue

        with controller.state.mutex:
            redraw = process_event(controller, event)

        if redraw:
            # Tell the main thread we need a redraw
            controller.redraw_event.set()
