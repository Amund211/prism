import logging
import re

from sidelay.state import OverlayState

logger = logging.getLogger()

RANK_REGEX = re.compile(r"\[[a-zA-Z\+]+\] ")


SETTING_USER_PREFIX = (
    "Game/net.minecraft.client.Minecraft (Client thread) Info Setting user: "
)

CHAT_PREFIX = "Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] "


def strip_until(line: str, *, until: str) -> str:
    """Remove the first occurrence of `until` and all characters before"""
    return line[line.find(until) + len(until) :].strip()


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
