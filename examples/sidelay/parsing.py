import logging
import re
from dataclasses import dataclass
from enum import Enum, auto, unique
from typing import Final, Literal, Optional, Union

logger = logging.getLogger()


RANK_REGEX = re.compile(r"\[[a-zA-Z\+]+\] ")


SETTING_USER_PREFIX = (
    "Game/net.minecraft.client.Minecraft (Client thread) Info Setting user: "
)

CHAT_PREFIX = "Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] "

PartyRole = Literal["leader", "moderators", "members"]


@unique
class EventType(Enum):
    # Initialization
    INITIALIZE_AS = auto()  # Initialize as the given username

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


@dataclass
class InitializeAsEvent:
    username: str
    event_type: Literal[EventType.INITIALIZE_AS] = EventType.INITIALIZE_AS


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


Event = Union[
    InitializeAsEvent,
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
]


def strip_until(line: str, *, until: str) -> str:
    """Remove the first occurrence of `until` and all characters before"""
    return line[line.find(until) + len(until) :].strip()


def remove_ranks(playerstring: str) -> str:
    """Remove all ranks from a string"""
    return RANK_REGEX.sub("", playerstring)


def parse_logline(logline: str) -> Optional[Event]:
    """Parse a log line to detect players leaving or joining the lobby/party"""
    if CHAT_PREFIX in logline:
        return parse_chat_message(strip_until(logline, until=CHAT_PREFIX))
    elif SETTING_USER_PREFIX in logline:
        username = strip_until(logline, until=SETTING_USER_PREFIX)
        return InitializeAsEvent(username)

    return None


def parse_chat_message(message: str) -> Optional[Event]:
    """
    Parse a chat message to detect players leaving or joining the lobby/party

    The message is assumed to be stripped of the "... Info [CHAT] " prefix:
    Messages should look like:
        'Player joined your party!'
    Not like:
        '...client.gui.GuiNewChat (Client thread) Info [CHAT] Player joined your party!'
    """
    # Lobby changes
    WHO_PREFIX = "ONLINE: "

    logger.debug(f"Chat message: '{message}'")

    if message.startswith(WHO_PREFIX):
        # Info [CHAT] ONLINE: <username1>, <username2>, ..., <usernameN>
        players = message.removeprefix(WHO_PREFIX).split(", ")
        return LobbyListEvent(players)

    if message.startswith("Sending you to "):
        return LobbySwapEvent()

    if " has joined (" in message:
        # Info [CHAT] <username> has joined (<x>/<N>)!
        # Someone joined the lobby -> Add them to the lobby
        logger.debug("Processing potential lobby join message")

        words = message.split(" ")
        if len(words) < 4:  # pragma: no cover
            # The message can not be <username> has joined (<x>/<N>)!
            logger.debug("Message is too short!")
            return None

        for word, target in zip(words[1:3], ("has", "joined")):
            if word != target:
                logger.debug("Message does not match target! {word=} != {target=}")
                return None

        username = words[0]

        lobby_fill_string = words[3]
        if not re.fullmatch(r"\(\d+\/\d+\)\!", lobby_fill_string):
            logger.debug("Fill string '{lobby_fill_string}' does not match '(x/N)!'")
            return None

        # Message is a join message
        prefix, suffix = lobby_fill_string.split("/")
        player_count = int(prefix.removeprefix("("))
        player_cap = int(suffix.removesuffix(")!"))

        return LobbyJoinEvent(
            username=username, player_count=player_count, player_cap=player_cap
        )

    if " has quit!" in message:
        # Info [CHAT] <username> has quit!
        # Someone left the lobby -> Remove them from the lobby
        logger.debug("Processing potential lobby leave message")

        words = message.split(" ")
        if len(words) < 3:  # pragma: no cover
            # The message can not be <username> has quit!
            logger.debug("Message is too short!")
            return None

        for word, target in zip(words[1:3], ("has", "quit!")):
            if word != target:
                logger.debug("Message does not match target! {word=} != {target=}")
                return None

        username = words[0]

        return LobbyLeaveEvent(username)

    # Party changes
    if message.startswith("You left the party."):
        # Info [CHAT] You left the party.
        return PartyDetachEvent()

    if message.startswith("You are not currently in a party."):
        # Info [CHAT] You are not currently in a party.
        return PartyDetachEvent()

    if " has disbanded the party!" in message:
        # Info [CHAT] [MVP++] Player1 has disbanded the party!
        clean = remove_ranks(message)
        words = clean.split(" ")

        if len(words) < 5:  # pragma: no cover
            # The message can not be <username> has disbanded the party!
            logger.debug("Message is too short!")
            return None

        for word, target in zip(words[1:], ("has", "disbanded", "the", "party!")):
            if word != target:
                logger.debug("Message does not match target! {word=} != {target=}")
                return None

        return PartyDetachEvent()

    if message.startswith("You have been kicked from the party by "):
        # Info [CHAT] You have been kicked from the party by [MVP+] <username>
        return PartyDetachEvent()

    PARTY_YOU_JOIN_PREFIX = "You have joined "
    if message.startswith(PARTY_YOU_JOIN_PREFIX):
        # Info [CHAT] You have joined [MVP++] <username>'s party!
        logger.debug("Processing potential party you join message")

        suffix = message.removeprefix(PARTY_YOU_JOIN_PREFIX)

        try:
            apostrophe_index = suffix.index("'")
        except ValueError:
            logging.error("Could not find apostrophe in string '{message}'")
            return None

        ranked_player_string = suffix[:apostrophe_index]
        username = remove_ranks(ranked_player_string)

        return PartyAttachEvent(username)

    PARTYING_WITH_PREFIX = "You'll be partying with: "
    if message.startswith(PARTYING_WITH_PREFIX):
        # Info [CHAT] You'll be partying with: Player2, [MVP++] Player3, [MVP+] Player4
        suffix = message.removeprefix(PARTYING_WITH_PREFIX)

        names = remove_ranks(suffix)

        return PartyJoinEvent(names.split(", "))

    if " joined the party" in message:
        # Info [CHAT] [VIP+] <username> joined the party.
        logger.debug("Processing potential party they join message")

        suffix = remove_ranks(message)

        words = suffix.split(" ")
        if len(words) < 4:  # pragma: no cover
            # The message can not be <username> joined the party
            logger.debug("Message is too short!")
            return None

        for word, target in zip(words[1:4], ("joined", "the", "party.")):
            if word != target:
                logger.debug("Message does not match target! {word=} != {target=}")
                return None

        username = words[0]

        return PartyJoinEvent([username])

    if " has left the party" in message:
        # Info [CHAT] [VIP+] <username> has left the party.
        logger.debug("Processing potential party they leave message")

        suffix = remove_ranks(message)

        words = suffix.split(" ")
        if len(words) < 5:  # pragma: no cover
            # The message can not be <username> has left the party
            logger.debug("Message is too short!")
            return None

        for word, target in zip(words[1:5], ("has", "left", "the", "party")):
            if not word.startswith(target):
                logger.debug("Message does not match target! {word=} != {target=}")
                return None

        username = words[0]

        return PartyLeaveEvent([username])

    if " has been removed from the party." in message:
        # Info [CHAT] [VIP+] <username> has been removed from the party.
        logger.debug("Processing potential party they kicked message")

        suffix = remove_ranks(message)

        words = suffix.split(" ")
        if len(words) < 7:  # pragma: no cover
            # The message can not be <username> has left the party
            logger.debug("Message is too short!")
            return None

        for word, target in zip(
            words[1:], ("has", "been", "removed", "from", "the", "party.")
        ):
            if word != target:
                logger.debug("Message does not match target! {word=} != {target=}")
                return None

        username = words[0]

        return PartyLeaveEvent([username])

    if " was removed from the party because they disconnected" in message:
        # [MVP+] Player1 was removed from the party because they disconnected"
        cleaned = remove_ranks(message)
        words = cleaned.split(" ")
        if len(words) < 9:  # pragma: no cover
            logger.debug("Message is too short!")
            return None

        for word, target in zip(
            words[1:],
            (
                "was",
                "removed",
                "from",
                "the",
                "party",
                "because",
                "they",
                "disconnected",
            ),
        ):
            if word != target:
                logger.debug("Message does not match target! {word=} != {target=}")
                return None

        username = words[0]

        return PartyLeaveEvent([username])

    PARTY_KICK_OFFLINE_PREFIX = "Kicked "
    if (
        message.startswith(PARTY_KICK_OFFLINE_PREFIX)
        and " because they were offline." in message
    ):
        # Info [CHAT] Kicked [VIP] <username1>, <username2> because they were offline.
        suffix = message.removeprefix(PARTY_KICK_OFFLINE_PREFIX)
        cleaned = remove_ranks(suffix)
        words = cleaned.split(" ")
        if len(words) < 5:  # pragma: no cover
            logger.debug("Message is too short!")
            return None

        for word, target in zip(words[-4:], ("because", "they", "were", "offline.")):
            if word != target:
                logger.debug("Message does not match target! {word=} != {target=}")
                return None

        usernames = " ".join(words[:-4]).split(", ")

        return PartyLeaveEvent(usernames)

    TRANSFER_PREFIX = "The party was transferred to "
    if message.startswith(TRANSFER_PREFIX):
        # Info [CHAT] ... transferred to [VIP] <someone> because [MVP++] <username> left
        suffix = message.removeprefix(TRANSFER_PREFIX)
        without_ranks = remove_ranks(suffix)

        # should be <someone> because <username> left
        words = without_ranks.split(" ")
        if len(words) < 4:
            logger.debug("Message is too short!")
            return None

        for word, target in zip(words[1::2], ("because", "left")):
            if not word.startswith(target):
                logger.debug("Message does not match target! {word=} != {target=}")
                return None

        username = words[2]

        return PartyLeaveEvent([username])
    """
    # noqa: W291
    Info [CHAT] -----------------------------
    Info [CHAT] Party Members (3)
    Info [CHAT] 
    Info [CHAT] Party Leader: [MVP++] <username> ●
    Info [CHAT] 
    Info [CHAT] Party Moderators: <username> ● 
    Info [CHAT] Party Members: <username> ● [VIP+] <username> ● 
    Info [CHAT] -----------------------------
    """

    if message.startswith("Party Members ("):
        # Info [CHAT] Party Members (<n>)
        # This is a response from /pl (/party list)

        return PartyListIncomingEvent()

    roles: Final = ("leader", "moderators", "members")

    for role in roles:
        # Info [CHAT] Party <Role>: [MVP++] <username> ●
        prefix = f"party {role}: ".title()
        if message.startswith(prefix):
            suffix = message.removeprefix(prefix)
            dirty_string = remove_ranks(suffix)
            clean_string = dirty_string.strip().replace(" ●", "")

            players = clean_string.split(" ")

            # I can't for the life of me get the literal types here
            return PartyMembershipListEvent(usernames=players, role=role)  # type:ignore

    return None
