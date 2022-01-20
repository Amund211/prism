import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Protocol

from examples.sidelay.parsing import Event, EventType, parse_logline

logger = logging.getLogger(__name__)


class SetNickname(Protocol):  # pragma: no cover
    def __call__(self, *, username: str, nick: str) -> None:
        ...


@dataclass
class OverlayState:
    """Dataclass holding the state of the overlay"""

    party_members: set[str]
    lobby_players: set[str]
    set_api_key: Callable[[str], None] = field(compare=False, repr=False)
    set_nickname: SetNickname = field(compare=False, repr=False)
    out_of_sync: bool = False
    in_queue: bool = False
    own_username: Optional[str] = None
    mutex: threading.Lock = field(
        default_factory=threading.Lock, init=False, compare=False, repr=False
    )

    def join_queue(self) -> None:
        """
        Join a queue by setting in_queue = True

        NOTE: Can modify the lobby, so call this before making any changes
        """
        if not self.in_queue:
            # This is a new queue -> clear the last lobby
            self.clear_lobby()

        self.in_queue = True

    def leave_queue(self) -> None:
        """
        Leave a queue by setting in_queue = False

        NOTE: The game starting counts as leaving the queue.
        """
        self.in_queue = False

    def add_to_party(self, username: str) -> None:
        """Add the given username to the party"""
        self.party_members.add(username)

    def remove_from_party(self, username: str) -> None:
        """Remove the given username from the party"""
        if username not in self.party_members:
            logger.warning(
                f"Tried removing {username} from the party, but they were not in it!"
            )
            return

        self.party_members.remove(username)

    def clear_party(self) -> None:
        """Remove all players from the party, except for yourself"""
        self.party_members.clear()

        if self.own_username is None:
            logger.warning("Own username is not set, party is now empty")
        else:
            self.add_to_party(self.own_username)

    def add_to_lobby(self, username: str) -> None:
        """Add the given username to the lobby"""
        self.lobby_players.add(username)

    def remove_from_lobby(self, username: str) -> None:
        """Remove the given username from the lobby"""
        if username not in self.lobby_players:
            logger.warning(
                f"Tried removing {username} from the lobby, but they were not in it!"
            )
            return

        self.lobby_players.remove(username)

    def set_lobby(self, new_lobby: Iterable[str]) -> None:
        """Set the lobby to be the given lobby"""
        self.lobby_players = set(new_lobby)

    def clear_lobby(self) -> None:
        """Remove all players from the lobby"""
        # Don't include yourself in the new lobby.
        # Your name usually appears as a join message anyway, and you may be nicked
        self.set_lobby([])


def update_state(state: OverlayState, event: Event) -> bool:
    """Update the state based on the event, return True if a redraw is desired"""
    if event.event_type is EventType.INITIALIZE_AS:
        if state.own_username is not None:
            logger.warning(
                f"Initializing as {event.username}, but "
                f"already initialized as {state.own_username}"
            )

        # Initializing means the player restarted -> clear the state
        state.own_username = event.username
        state.clear_party()
        state.clear_lobby()

        logger.info(f"Playing as {state.own_username}. Cleared party and lobby.")
        return True

    if event.event_type is EventType.NEW_NICKNAME:
        # User got a new nickname
        logger.info("Setting new nickname")
        if state.own_username is None:
            logger.warning(
                "Own username is not set, could not add denick entry for {event.nick}."
            )
        else:
            state.set_nickname(username=state.own_username, nick=event.nick)

        # We should redraw so that we can properly denick ourself
        return True

    if event.event_type is EventType.LOBBY_SWAP:
        # Changed lobby -> clear the lobby
        logger.info("Clearing the lobby")
        state.clear_lobby()
        state.leave_queue()

        return True

    if event.event_type is EventType.LOBBY_LIST:
        # Results from /who -> override lobby_players
        logger.info("Updating lobby players from who command")
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
                logger.info("Too many players in lobby. Clearing.")
                state.clear_lobby()
                state.add_to_lobby(event.username)

                # Clearing the lobby may have gotten us back in sync
                out_of_sync = event.player_count != len(state.lobby_players)

            state.out_of_sync = out_of_sync
        else:
            # We are in sync now
            state.out_of_sync = False

        logger.info(f"{event.username} joined your lobby")

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

    if event.event_type is EventType.END_BEDWARS_GAME:
        # Bedwars game has ended
        logger.info("Bedwars game ended")
        state.clear_lobby()

        return True

    if event.event_type is EventType.NEW_API_KEY:
        # User got a new API key
        logger.info("Setting new API key")
        state.set_api_key(event.key)

        return False


def fast_forward_state(state: OverlayState, loglines: Iterable[str]) -> None:
    """Process the state changes for each logline without outputting anything"""
    for line in loglines:
        event = parse_logline(line)

        if event is None:
            continue

        update_state(state, event)
