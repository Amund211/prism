import logging
import re
from collections.abc import Sequence
from typing import Final

from examples.overlay.events import (
    ChatEvent,
    ClientEvent,
    EndBedwarsGameEvent,
    Event,
    InitializeAsEvent,
    LobbyJoinEvent,
    LobbyLeaveEvent,
    LobbyListEvent,
    LobbySwapEvent,
    NewAPIKeyEvent,
    NewNicknameEvent,
    PartyAttachEvent,
    PartyDetachEvent,
    PartyJoinEvent,
    PartyLeaveEvent,
    PartyListIncomingEvent,
    PartyMembershipListEvent,
    StartBedwarsGameEvent,
    WhisperCommandSetNickEvent,
)

logger = logging.getLogger(__name__)


RANK_REGEX = re.compile(r"\[[a-zA-Z\+]+\] ")


CLIENT_INFO_PREFIXES = (
    "(Client thread) Info ",  # Vanilla and forge launcher_log.txt
    "[Client thread/INFO]: ",  # Vanilla and forge latest.log
    "INFO]: [LC] ",  # Lunar client
    "[Client thread/INFO]: [LC]",  # New lunar
)

# Vanilla and forge
CHAT_PREFIXES = (
    "(Client thread) Info [CHAT] ",  # Vanilla and forge launcher_log.txt
    "[Client thread/INFO]: [CHAT] ",  # Vanilla and forge latest.log + Lunar client
)


def strip_until(line: str, *, until: str) -> str:
    """Remove the first occurrence of `until` and all characters before"""
    return line[line.index(until) + len(until) :].strip()


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


def get_highest_index(source: str, *strings: str) -> str | None:
    """
    Return the substring that ends at the highest index in source

    If none of the strings are strings of source, return None.
    """

    # Store result intermediately to circumvent mypy bug
    # https://github.com/python/mypy/issues/5874
    result = max(
        filter(lambda s: s in source, strings),
        key=lambda s: source.index(s) + len(s),
        default=None,
    )

    return result


def parse_logline(logline: str) -> Event | None:
    """Parse a log line to detect players leaving or joining the lobby/party"""

    # Get the lowest index of any of the chat prefixes to find the message
    # This prevents users being able to inject a payload by typing a message
    # starting with the log prefix
    chat_prefix = get_lowest_index(logline, *CHAT_PREFIXES)
    if chat_prefix is not None:
        return parse_chat_message(strip_until(logline, until=chat_prefix))

    # Since we have assumed that we have filtered all chatlines, these lines are not
    # user controlled, and we are safe to not use the lowest index.
    # Instead we use the highest index as some prefixes share a prefix.
    client_info_prefix = get_highest_index(logline, *CLIENT_INFO_PREFIXES)
    if client_info_prefix is not None:
        return parse_client_info(strip_until(logline, until=client_info_prefix))

    return None


def parse_client_info(info: str) -> ClientEvent | None:
    SETTING_USER_PREFIX = "Setting user: "
    if info.startswith(SETTING_USER_PREFIX):
        username = strip_until(info, until=SETTING_USER_PREFIX)
        return InitializeAsEvent(username)

    return None


def words_match(words: Sequence[str], target: str) -> bool:
    """Return true if `words` matches the space separated words in `target`"""
    joined_words = " ".join(words)
    full_match = joined_words == target

    if not full_match:
        logger.debug("Message does not match target! {joined_words=} != {target=}")

    return full_match


def parse_chat_message(message: str) -> ChatEvent | None:
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

        logger.debug(f"Parsing passed. New key: {words[5]}")
        return NewAPIKeyEvent(words[5])

    if message.startswith("You are now nicked as "):
        # Info [CHAT] You are now nicked as AmazingNick!
        logger.debug("Processing potential new nickname")
        words = message.split(" ")
        if not words_match(words[:-1], "You are now nicked as"):
            return None

        if words[-1][-1] != "!":
            return None

        logger.debug(f"Parsing passed. New nickname: {words[-1][:-1]}")
        return NewNicknameEvent(words[-1][:-1])

    if message.startswith("Sending you to "):
        logger.debug("Parsing passed. Swapping lobby")
        return LobbySwapEvent()

    if message == "You were sent to a lobby because someone in your party left!":
        logger.debug("Parsing passed. Swapping lobby")
        return LobbySwapEvent()

    # NOTE: This also appears at the end of a game, but before endgameevent is sent
    if message.startswith("Bed Wars"):
        logger.debug("Parsing passed. Starting game")
        return StartBedwarsGameEvent()

    if message.startswith("1st Killer "):
        # Info [CHAT]                     1st Killer - [MVP+] Player1 - 7
        logger.debug("Parsing passed. Ending game")
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
            logger.debug(f"Fill string '{lobby_fill_string}' does not match '(x/N)!'")
            return None

        # Message is a join message
        prefix, suffix = lobby_fill_string.split("/")
        player_count = int(prefix.removeprefix("("))
        player_cap = int(suffix.removesuffix(")!"))

        logger.debug(f"Parsing passed. {username} joined ({player_count}/{player_cap})")
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

        logger.debug(f"Parsing passed. {username} quit")
        return LobbyLeaveEvent(username)

    # Party changes
    if message.startswith("You left the party."):
        # Info [CHAT] You left the party.
        logger.debug("Parsing passed. You left the party")
        return PartyDetachEvent()

    if message.startswith("You are not currently in a party."):
        # Info [CHAT] You are not currently in a party.
        logger.debug("Parsing passed. You are not in a party")
        return PartyDetachEvent()

    if (
        message
        == "The party was disbanded because all invites expired and the party was empty"
    ):
        # Info [CHAT] The party was disbanded because all invites expired
        # and the party was empty
        logger.debug("Parsing passed. Party disbanded")
        return PartyDetachEvent()

    if " has disbanded the party!" in message:
        # Info [CHAT] [MVP++] Player1 has disbanded the party!
        logger.debug("Processing potential party disband message")
        clean = remove_ranks(message)
        words = clean.split(" ")

        if len(words) < 5:  # pragma: no cover
            # The message can not be <username> has disbanded the party!
            logger.debug("Message is too short!")
            return None

        if not words_match(words[1:], "has disbanded the party!"):
            return None

        logger.debug(f"Parsing passed. {words[0]} disbanded the party")
        return PartyDetachEvent()

    if message.startswith("You have been kicked from the party by "):
        # Info [CHAT] You have been kicked from the party by [MVP+] <username>
        logger.debug("Parsing passed. You were kicked")
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

        logger.debug(f"Parsing passed. You joined {username}'s party")
        return PartyAttachEvent(username)

    PARTYING_WITH_PREFIX = "You'll be partying with: "
    if message.startswith(PARTYING_WITH_PREFIX):
        # Info [CHAT] You'll be partying with: Player2, [MVP++] Player3, [MVP+] Player4
        logger.debug("Processing potential partying with message")
        suffix = message.removeprefix(PARTYING_WITH_PREFIX)

        names = remove_ranks(suffix)

        logger.debug(f"Parsing passed. Partying with {names}")
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

        logger.debug(f"Parsing passed. {username} joined the party")
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

        logger.debug(f"Parsing passed. {username} left the party")
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

        logger.debug(f"Parsing passed. {username} was kicked")
        return PartyLeaveEvent([username])

    if " was removed from the party because they disconnected" in message:
        # [MVP+] Player1 was removed from the party because they disconnected"
        logger.debug("Processing potential party they disconnected message")
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

        logger.debug(f"Parsing passed. {username} was kicked for disconnecting")
        return PartyLeaveEvent([username])

    PARTY_KICK_OFFLINE_PREFIX = "Kicked "
    if (
        message.startswith(PARTY_KICK_OFFLINE_PREFIX)
        and " because they were offline." in message
    ):
        logger.debug("Processing potential party kickoffline message")
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

        logger.debug(f"Parsing passed. {', '.join(usernames)} were kickoffline'd")
        return PartyLeaveEvent(usernames)

    TRANSFER_PREFIX = "The party was transferred to "
    if message.startswith(TRANSFER_PREFIX):
        # Info [CHAT] ... transferred to [VIP] <someone> because [MVP++] <username> left
        logger.debug("Processing potential party transfer leave message")
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

        logger.debug(f"Parsing passed. {username} left")
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

        logger.debug("Parsing passed. Party list response incoming")
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

            logger.debug(f"Parsing passed. Party {role=} are {players}")
            # I can't for the life of me get the literal types here
            return PartyMembershipListEvent(usernames=players, role=role)  # type:ignore

    WHISPER_COMMAND_PREFIX = "Can't find a player by the name of '!"
    if message.startswith(WHISPER_COMMAND_PREFIX):
        logger.debug("Processing potential whisper command")
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

            logger.debug(f"Parsing passed. Setting nick {nick=}->{username=}")
            return WhisperCommandSetNickEvent(
                nick=nick, username=username if username else None
            )

        return None

    return None
