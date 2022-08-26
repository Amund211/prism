from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto, unique
from typing import TYPE_CHECKING, Literal, Union

if TYPE_CHECKING:  # pragma: no cover
    from examples.overlay.controller import OverlayController


logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


PartyRole = Literal["leader", "moderators", "members"]


@unique
class EventType(Enum):
    # Initialization
    INITIALIZE_AS = auto()  # Initialize as the given username

    # New nickname (/nick reuse)
    NEW_NICKNAME = auto()

    # Lobby join/leave
    LOBBY_SWAP = auto()  # You join a new lobby
    LOBBY_JOIN = auto()  # Someone joins your lobby
    LOBBY_LEAVE = auto()  # Someone leaves your lobby

    # /who
    LOBBY_LIST = auto()  # You get a list of all players in your lobby

    # Party join/leave
    PARTY_ATTACH = auto()  # You join a party
    PARTY_DETACH = auto()  # You leave a party
    PARTY_JOIN = auto()  # Someone joins your party
    PARTY_LEAVE = auto()  # Someone leaves your party

    # /party list (/pl)
    PARTY_LIST_INCOMING = auto()  # The header of the party table
    PARTY_ROLE_LIST = auto()  # List of members or moderators, or the leader

    # Games
    START_BEDWARS_GAME = auto()  # A bedwars game has started
    END_BEDWARS_GAME = auto()  # A bedwars game has ended

    # New API key
    NEW_API_KEY = auto()  # New API key in chat (/api new)

    # Commands /w !<command>
    WHISPER_COMMAND_SET_NICK = auto()


@dataclass
class InitializeAsEvent:
    username: str
    event_type: Literal[EventType.INITIALIZE_AS] = EventType.INITIALIZE_AS


@dataclass
class NewNicknameEvent:
    nick: str
    event_type: Literal[EventType.NEW_NICKNAME] = EventType.NEW_NICKNAME


@dataclass
class LobbySwapEvent:
    event_type: Literal[EventType.LOBBY_SWAP] = EventType.LOBBY_SWAP


@dataclass
class LobbyJoinEvent:
    username: str
    player_count: int
    player_cap: int
    event_type: Literal[EventType.LOBBY_JOIN] = EventType.LOBBY_JOIN


@dataclass
class LobbyLeaveEvent:
    username: str
    event_type: Literal[EventType.LOBBY_LEAVE] = EventType.LOBBY_LEAVE


@dataclass
class LobbyListEvent:
    usernames: list[str]
    event_type: Literal[EventType.LOBBY_LIST] = EventType.LOBBY_LIST


@dataclass
class PartyAttachEvent:
    username: str  # Leader
    event_type: Literal[EventType.PARTY_ATTACH] = EventType.PARTY_ATTACH


@dataclass
class PartyDetachEvent:
    event_type: Literal[EventType.PARTY_DETACH] = EventType.PARTY_DETACH


@dataclass
class PartyJoinEvent:
    usernames: list[str]
    event_type: Literal[EventType.PARTY_JOIN] = EventType.PARTY_JOIN


@dataclass
class PartyLeaveEvent:
    usernames: list[str]
    event_type: Literal[EventType.PARTY_LEAVE] = EventType.PARTY_LEAVE


@dataclass
class PartyListIncomingEvent:
    event_type: Literal[EventType.PARTY_LIST_INCOMING] = EventType.PARTY_LIST_INCOMING


@dataclass
class PartyMembershipListEvent:
    usernames: list[str]
    role: PartyRole  # The users' roles
    event_type: Literal[EventType.PARTY_ROLE_LIST] = EventType.PARTY_ROLE_LIST


@dataclass
class StartBedwarsGameEvent:
    event_type: Literal[EventType.START_BEDWARS_GAME] = EventType.START_BEDWARS_GAME


@dataclass
class EndBedwarsGameEvent:
    event_type: Literal[EventType.END_BEDWARS_GAME] = EventType.END_BEDWARS_GAME


@dataclass
class NewAPIKeyEvent:
    key: str
    event_type: Literal[EventType.NEW_API_KEY] = EventType.NEW_API_KEY


@unique
class WhisperCommandType(Enum):
    SET_NICK = auto()


@dataclass
class WhisperCommandSetNickEvent:
    nick: str
    username: str | None
    event_type: Literal[
        EventType.WHISPER_COMMAND_SET_NICK
    ] = EventType.WHISPER_COMMAND_SET_NICK


ClientEvent = Union[
    InitializeAsEvent,
]

ChatEvent = Union[
    NewNicknameEvent,
    LobbySwapEvent,
    LobbyJoinEvent,
    LobbyLeaveEvent,
    LobbyListEvent,
    PartyAttachEvent,
    PartyDetachEvent,
    PartyJoinEvent,
    PartyLeaveEvent,
    PartyListIncomingEvent,
    PartyMembershipListEvent,
    StartBedwarsGameEvent,
    EndBedwarsGameEvent,
    NewAPIKeyEvent,
    WhisperCommandSetNickEvent,
]

Event = Union[ClientEvent, ChatEvent]


def process_event(controller: OverlayController, event: Event) -> bool:
    """Update the state based on the event, return True if a redraw is desired"""
    from examples.overlay.behaviour import set_hypixel_api_key, set_nickname

    state = controller.state

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
            set_nickname(
                username=state.own_username, nick=event.nick, controller=controller
            )

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

    if event.event_type is EventType.END_BEDWARS_GAME:
        # Bedwars game has ended
        logger.info("Bedwars game ended")
        state.clear_lobby()

        return True

    if event.event_type is EventType.NEW_API_KEY:
        # User got a new API key
        logger.info("Setting new API key")
        set_hypixel_api_key(event.key, controller)

        return False

    if event.event_type is EventType.WHISPER_COMMAND_SET_NICK:
        # User set a nick with /w !nick=username
        set_nickname(username=event.username, nick=event.nick, controller=controller)
        return True
