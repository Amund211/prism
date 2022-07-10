import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto, unique
from typing import Final, Literal, Union

logger = logging.getLogger(__name__)


RANK_REGEX = re.compile(r"\[[a-zA-Z\+]+\] ")


# Vanilla and forge
SETTING_USER_PREFIX = "(Client thread) Info Setting user: "
SETTING_USER_PREFIX_LUNAR = "INFO]: [LC] Setting user: "

# Vanilla and forge
CHAT_PREFIX = "(Client thread) Info [CHAT] "
CHAT_PREFIX_LUNAR = "[Client thread/INFO]: [CHAT] "

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


Event = Union[
    InitializeAsEvent,
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


def strip_until(line: str, *, until: str) -> str:
    """Remove the first occurrence of `until` and all characters before"""
    return line[line.find(until) + len(until) :].strip()


def remove_ranks(playerstring: str) -> str:
    """Remove all ranks from a string"""
    return RANK_REGEX.sub("", playerstring)


def get_lowest_index(source: str, *strings: str) -> str | None:
    """
    Return the substring that ends at the lowest index in source

    If none of the strings are strings of source, return None.
    """

    # Store result intermediately to circumvent mypy bug
    # https://github.com/python/mypy/issues/5874
    result = min(
        filter(lambda s: s in source, strings),
        key=lambda s: source.index(s) + len(s),
        default=None,
    )

    return result


def parse_logline(logline: str) -> Event | None:
    """Parse a log line to detect players leaving or joining the lobby/party"""

    chat_prefix = get_lowest_index(logline, CHAT_PREFIX, CHAT_PREFIX_LUNAR)
    if chat_prefix is not None:
        return parse_chat_message(strip_until(logline, until=chat_prefix))

    setting_user_prefix = get_lowest_index(
        logline, SETTING_USER_PREFIX, SETTING_USER_PREFIX_LUNAR
    )
    if setting_user_prefix is not None:
        username = strip_until(logline, until=setting_user_prefix)
        return InitializeAsEvent(username)

    return None


def words_match(words: Sequence[str], target: str) -> bool:
    """Return true if `words` matches the space separated words in `target`"""
    joined_words = " ".join(words)
    full_match = joined_words == target

    if not full_match:
        logger.debug("Message does not match target! {joined_words=} != {target=}")

    return full_match


def parse_chat_message(message: str) -> Event | None:
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

    if message.startswith("Your new API key is "):
        # Info [CHAT] Your new API key is deadbeef-ae10-4d07-25f6-f23130b92652
        logger.debug("Processing potential new API key")
        words = message.split(" ")
        if len(words) != 6:
            logger.debug("Message too long")
            return None

        return NewAPIKeyEvent(words[5])

    if message.startswith("You are now nicked as "):
        # Info [CHAT] You are now nicked as AmazingNick!
        words = message.split(" ")
        if not words_match(words[:-1], "You are now nicked as"):
            return None

        if words[-1][-1] != "!":
            return None

        return NewNicknameEvent(words[-1][:-1])

    if message.startswith("Sending you to "):
        return LobbySwapEvent()

    if message == "You were sent to a lobby because someone in your party left!":
        return LobbySwapEvent()

    if message.startswith("Bed Wars"):
        return StartBedwarsGameEvent()

    if message.startswith("1st Killer "):
        # Info [CHAT]                     1st Killer - [MVP+] Player1 - 7
        return EndBedwarsGameEvent()

    if " has joined (" in message:
        # Info [CHAT] <username> has joined (<x>/<N>)!
        # Someone joined the lobby -> Add them to the lobby
        logger.debug("Processing potential lobby join message")

        words = message.split(" ")
        if len(words) < 4:  # pragma: no cover
            # The message can not be <username> has joined (<x>/<N>)!
            logger.debug("Message is too short!")
            return None

        if not words_match(words[1:3], "has joined"):
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

        if not words_match(words[1:3], "has quit!"):
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

    if (
        message
        == "The party was disbanded because all invites expired and the party was empty"
    ):
        # Info [CHAT] The party was disbanded because all invites expired
        # and the party was empty
        return PartyDetachEvent()

    if " has disbanded the party!" in message:
        # Info [CHAT] [MVP++] Player1 has disbanded the party!
        clean = remove_ranks(message)
        words = clean.split(" ")

        if len(words) < 5:  # pragma: no cover
            # The message can not be <username> has disbanded the party!
            logger.debug("Message is too short!")
            return None

        if not words_match(words[1:], "has disbanded the party!"):
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
            logging.debug(f"Could not find apostrophe in string '{message}'")
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

        if not words_match(words[1:4], "joined the party."):
            return None

        username = words[0]

        return PartyJoinEvent([username])

    if " has left the party" in message:
        # Info [CHAT] [VIP+] <username> has left the party.
        logger.debug("Processing potential party they leave message")

        suffix = remove_ranks(message)

        words = suffix.split(" ")
        if len(words) < 5:  # pragma: no cover
            # The message can not be <username> has left the party.
            logger.debug("Message is too short!")
            return None

        if not words_match(words[1:5], "has left the party."):
            return None

        username = words[0]

        return PartyLeaveEvent([username])

    if " has been removed from the party." in message:
        # Info [CHAT] [VIP+] <username> has been removed from the party.
        logger.debug("Processing potential party they kicked message")

        suffix = remove_ranks(message)

        words = suffix.split(" ")
        if len(words) < 7:  # pragma: no cover
            # The message can not be <username> has been removed from the party.
            logger.debug("Message is too short!")
            return None

        if not words_match(words[1:], "has been removed from the party."):
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

        if not words_match(
            words[1:], "was removed from the party because they disconnected"
        ):
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

        if not words_match(words[-4:], "because they were offline."):
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

        if not words_match(words[1::2], "because left"):
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

    WHISPER_COMMAND_PREFIX = "Can't find a player by the name of '!"
    if message.startswith(WHISPER_COMMAND_PREFIX):
        command = message.removeprefix(WHISPER_COMMAND_PREFIX)
        if not command:
            logger.debug("Whisper command too short")
            return None

        if command[-1] != "'":
            logger.debug("Whisper command missing closing '")
            return None

        command = command[:-1]

        if "=" in command:
            arguments = command.split("=")
            if len(arguments) != 2:
                logger.debug("Whisper setnick command got too many arguments")
                return None

            nick, username = arguments

            return WhisperCommandSetNickEvent(
                nick=nick, username=username if username else None
            )

        return None

    return None
