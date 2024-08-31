from dataclasses import dataclass
from enum import Enum, auto, unique
from typing import Literal, Union

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
    BEDWARS_GAME_STARTING_SOON = auto()  # A bedwars game is starting soon
    START_BEDWARS_GAME = auto()  # A bedwars game has started
    BEDWARS_FINAL_KILL = auto()  # A final kill in bedwars
    BEDWARS_DISCONNECT = auto()  # A player disconnected in bedwars
    BEDWARS_RECONNECT = auto()  # A player reconnected in bedwars
    END_BEDWARS_GAME = auto()  # A bedwars game has ended

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
class BedwarsGameStartingSoonEvent:
    seconds: int
    event_type: Literal[EventType.BEDWARS_GAME_STARTING_SOON] = (
        EventType.BEDWARS_GAME_STARTING_SOON
    )


@dataclass
class StartBedwarsGameEvent:
    event_type: Literal[EventType.START_BEDWARS_GAME] = EventType.START_BEDWARS_GAME


@dataclass
class BedwarsFinalKillEvent:
    dead_player: str
    raw_message: str
    event_type: Literal[EventType.BEDWARS_FINAL_KILL] = EventType.BEDWARS_FINAL_KILL


@dataclass
class BedwarsDisconnectEvent:
    username: str
    event_type: Literal[EventType.BEDWARS_DISCONNECT] = EventType.BEDWARS_DISCONNECT


@dataclass
class BedwarsReconnectEvent:
    username: str
    event_type: Literal[EventType.BEDWARS_RECONNECT] = EventType.BEDWARS_RECONNECT


@dataclass
class EndBedwarsGameEvent:
    event_type: Literal[EventType.END_BEDWARS_GAME] = EventType.END_BEDWARS_GAME


@unique
class WhisperCommandType(Enum):
    SET_NICK = auto()


@dataclass
class WhisperCommandSetNickEvent:
    nick: str
    username: str | None
    event_type: Literal[EventType.WHISPER_COMMAND_SET_NICK] = (
        EventType.WHISPER_COMMAND_SET_NICK
    )


ClientEvent = InitializeAsEvent

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
    BedwarsGameStartingSoonEvent,
    StartBedwarsGameEvent,
    BedwarsFinalKillEvent,
    BedwarsDisconnectEvent,
    BedwarsReconnectEvent,
    EndBedwarsGameEvent,
    WhisperCommandSetNickEvent,
]

Event = Union[ClientEvent, ChatEvent]
