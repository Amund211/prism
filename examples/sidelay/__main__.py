"""
Search for /who responses in the logfile and print the found users' stats

Run from the examples dir by `python -m sidelay <path-to-logfile>`

Example string printed to logfile when typing /who:
'[Info: 2021-10-29 15:29:33.059151572: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] ONLINE: The_TOXIC__, T_T0xic, maskaom, NomexxD, Killerluise, Fruce_, 3Bitek, OhCradle, DanceMonky, Sweeetnesss, jbzn, squashypeas, Skydeaf, serocore'  # noqa: E501
"""

import logging
import re
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Optional, TextIO

from sidelay.printing import print_stats_table
from sidelay.stats import get_bedwars_stats

logging.basicConfig()
logger = logging.getLogger()

TESTING = False
CLEAR_BETWEEN_DRAWS = True

RANK_REGEX = re.compile(r"\[[a-zA-Z\+]+\] ")


SETTING_USER_PREFIX = (
    "Game/net.minecraft.client.Minecraft (Client thread) Info Setting user: "
)

CHAT_PREFIX = "Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] "


@dataclass
class OverlayState:
    """Dataclass holding the state of the overlay"""

    party_members: set[str]  # NOTE: lower case
    lobby_players: set[str]
    out_of_sync: bool = False
    own_username: Optional[str] = None

    def add_to_party(self, username: str) -> None:
        """Add the given username to the party"""
        self.party_members.add(username.lower())

    def remove_from_party(self, username: str) -> None:
        """Remove the given username from the party"""
        if username.lower() not in self.party_members:
            logger.error(
                f"Tried removing {username} from the party, but they were not in it!"
            )
            return

        self.party_members.remove(username.lower())

    def clear_party(self) -> None:
        """Remove all players from the party, except for yourself"""
        self.party_members.clear()

        if self.own_username is None:
            logger.warning("Own username is not set, party is now empty")
        else:
            self.party_members.add(self.own_username.lower())

    def add_to_lobby(self, username: str) -> None:
        """Add the given username to the lobby"""
        self.lobby_players.add(username)

    def remove_from_lobby(self, username: str) -> None:
        """Remove the given username from the lobby"""
        if username not in self.lobby_players:
            logger.error(
                f"Tried removing {username} from the lobby, but they were not in it!"
            )
            return

        self.lobby_players.remove(username)

    def set_lobby(self, new_lobby: Iterable[str]) -> None:
        """Set the lobby to be the given lobby"""
        self.lobby_players = set(new_lobby)


def strip_until(line: str, *, until: str) -> str:
    """Remove the first occurrence of `until` and all characters before"""
    return line[line.find(until) + len(until) :].strip()


def follow(thefile: TextIO) -> Iterable[str]:
    thefile.seek(0, 2)
    while True:
        line = thefile.readline()
        if not line:
            time.sleep(0.01)
            continue
        yield line


def remove_ranks(playerstring: str) -> str:
    """Remove all ranks from a string"""
    return RANK_REGEX.sub("", playerstring)


def process_chat_message(message: str, state: OverlayState) -> bool:
    """Look for potential state changes in a chat message and perform them"""
    # Lobby changes
    WHO_PREFIX = "ONLINE: "

    logger.debug(f"Chat message: '{message}'")

    if message.startswith(WHO_PREFIX):
        # Info [CHAT] ONLINE: <username1>, <username2>, ..., <usernameN>
        # Results from /who -> override lobby_players
        logger.info("Updating lobby players from who command")
        players = message.removeprefix(WHO_PREFIX).split(", ")
        state.set_lobby(players)
        state.out_of_sync = False

        return True

    if " has joined (" in message:
        # Info [CHAT] <username> has joined (<x>/<N>)!
        # Someone joined the lobby -> Add them to the lobby
        logger.debug("Processing potential lobby join message")

        words = message.split(" ")
        if len(words) < 4:
            # The message can not be <username> has joined (<x>/<N>)!
            logger.debug("Message is too short!")
            return False

        for word, target in zip(words[1:3], ("has", "joined")):
            if word != target:
                logger.debug("Message does not match target! {word=} != {target=}")
                return False

        lobby_fill_string = words[3]
        if not re.fullmatch(r"\(\d+\/\d+\)\!", lobby_fill_string):
            logger.debug("Fill string '{lobby_fill_string}' does not match '(x/N)!'")
            return False

        # Message is a join message
        prefix, suffix = lobby_fill_string.split("/")
        player_count = int(prefix.removeprefix("("))
        player_cap = int(suffix.removesuffix(")!"))

        if player_count != len(state.lobby_players) + 1:
            # We are out of sync with the lobby.
            # This happens when you first join a lobby, as the previous lobby is
            # never cleared. It could also be due to a bug.
            logger.debug(
                "Player count out of sync. Clearing the lobby. Please use /who"
            )

            state.out_of_sync = True
            state.set_lobby(state.party_members)

            redraw = True  # in case the next check fails, we still want to redraw
        else:
            # If we were out of sync we want to redraw, because we are in sync now
            redraw = state.out_of_sync
            state.out_of_sync = False

        if player_cap < 8:
            logger.debug("Gamemode has too few players to be bedwars. Skipping.")
            return redraw

        username = words[0]

        state.add_to_lobby(username)

        logger.info(f"{username} joined your lobby")

        return True

    if " has quit!" in message:
        # Info [CHAT] <username> has quit!
        # Someone left the lobby -> Remove them from the lobby
        logger.debug("Processing potential lobby leave message")

        words = message.split(" ")
        if len(words) < 3:
            # The message can not be <username> has quit!
            logger.debug("Message is too short!")
            return False

        for word, target in zip(words[1:3], ("has", "quit!")):
            if word != target:
                logger.debug("Message does not match target! {word=} != {target=}")
                return False

        username = words[0]

        state.remove_from_lobby(username)

        logger.info(f"{username} left your lobby")

        return True

    # Party changes
    if message.startswith("You left the party."):
        # Info [CHAT] You left the party.
        # Leaving the party -> remove all but yourself from the party
        logger.info("Leaving the party, clearing all members")

        state.clear_party()

        return True

    PARTY_YOU_JOIN_PREFIX = "You have joined "
    if message.startswith(PARTY_YOU_JOIN_PREFIX):
        # Info [CHAT] You have joined [MVP++] <username>'s party!
        # You joined a player's party -> add them to your party
        logger.debug("Processing potential party you join message")

        suffix = message.removeprefix(PARTY_YOU_JOIN_PREFIX)

        try:
            apostrophe_index = suffix.index("'")
        except ValueError:
            logging.error("Could not find apostrophe in string '{message}'")
            return False

        ranked_player_string = suffix[:apostrophe_index]
        username = remove_ranks(ranked_player_string)

        state.clear_party()
        state.add_to_party(username)

        logger.info(f"Joined {username}'s party. Adding you and them to your party.")

        return True

    if " joined the party" in message:
        # Info [CHAT] [VIP+] <username> joined the party.
        # Someone joined your party -> add them to your party
        logger.debug("Processing potential party they join message")

        suffix = remove_ranks(message)

        words = suffix.split(" ")
        if len(words) < 4:
            # The message can not be <username> joined the party
            logger.debug("Message is too short!")
            return False

        for word, target in zip(words[1:4], ("joined", "the", "party.")):
            if word != target:
                logger.debug("Message does not match target! {word=} != {target=}")
                return False

        username = words[0]

        state.add_to_party(username)

        logger.info(f"{username} joined your party")

        return True

    if " left the party" in message:
        # Info [CHAT] [VIP+] <username> left the party.
        # Someone left your party -> remove them from your party
        logger.debug("Processing potential party they leave message")

        suffix = remove_ranks(message)

        words = suffix.split(" ")
        if len(words) < 4:
            # The message can not be <username> left the party
            logger.debug("Message is too short!")
            return False

        for word, target in zip(words[1:4], ("left", "the", "party")):
            if not word.startswith(target):
                logger.debug("Message does not match target! {word=} != {target=}")
                return False

        username = words[0]

        state.remove_from_party(username)

        logger.info(f"{username} left your party")

        return True

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
        # In the following lines we will get all the party members -> clear the party
        logger.debug(
            "Receiving response from /pl -> clearing party and awaiting further data"
        )

        state.clear_party()

        return False  # No need to redraw as we're waiting for further input

    PARTY_LEADER_PREFIX = "Party Leader: "
    PARTY_MODERATORS_PREFIX = "Party Moderators: "
    PARTY_MEMBERS_PREFIX = "Party Members: "
    for prefix in (PARTY_LEADER_PREFIX, PARTY_MODERATORS_PREFIX, PARTY_MEMBERS_PREFIX):
        # Info [CHAT] Party <role>: [MVP++] <username> ●
        if message.startswith(prefix):
            logger.debug(f"Updating party members from {prefix.split(' ')[2]}")

            suffix = message.removeprefix(prefix)
            dirty_string = remove_ranks(suffix)
            clean_string = dirty_string.strip().replace(" ●", "")

            players = clean_string.split(" ")
            logger.info(f"Adding party members {', '.join(players)} from /pl")

            for player in players:
                state.add_to_party(player)

            return True
    # TODO:
    #   getting kicked
    #   other people getting kicked
    #   other people getting afk'd
    #   party disband

    return False


def process_loglines(loglines: Iterable[str]) -> None:
    """Process the state changes for each logline and redraw the screen if neccessary"""
    state = OverlayState(lobby_players=set(), party_members=set())

    for line in loglines:
        redraw = False
        if CHAT_PREFIX in line:
            redraw = process_chat_message(
                message=strip_until(line, until=CHAT_PREFIX), state=state
            )
        elif SETTING_USER_PREFIX in line:
            new_username = strip_until(line, until=SETTING_USER_PREFIX)

            if state.own_username is not None:
                logging.warning(
                    f"Initializing as {new_username}, but "
                    f"already initialized as {state.own_username}"
                )

            # Initializing means the player restarted -> clear the state
            state.own_username = new_username
            state.clear_party()
            state.set_lobby(set(state.own_username))

            logger.info(f"Playing as {state.own_username}. Cleared party and lobby.")
            redraw = True

        if redraw:
            logger.info(f"Party = {', '.join(state.party_members)}")
            logger.info(f"Lobby = {', '.join(state.lobby_players)}")

            stats = [get_bedwars_stats(player) for player in state.lobby_players]

            print_stats_table(
                stats=stats,
                party_members=state.party_members,
                out_of_sync=state.out_of_sync,
                clear_between_draws=CLEAR_BETWEEN_DRAWS,
            )


def watch_from_logfile(logpath: str) -> None:
    """Use the overlay on an active logfile"""
    with open(logpath, "r") as logfile:
        loglines = follow(logfile)
        process_loglines(loglines)


def test() -> None:
    """Test the implementation on a static logfile"""
    global TESTING, CLEAR_BETWEEN_DRAWS

    TESTING = True
    CLEAR_BETWEEN_DRAWS = False

    logger.setLevel(logging.DEBUG)

    assert len(sys.argv) >= 3

    with open(sys.argv[2], "r") as logfile:
        loglines = logfile
        process_loglines(loglines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Must provide a path to the logfile!", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "test":
        test()
    else:
        watch_from_logfile(sys.argv[1])
