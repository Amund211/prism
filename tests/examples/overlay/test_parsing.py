# Too many long lines in this file
# flake8: noqa
from typing import Sequence

import pytest

from examples.overlay.parsing import (
    CHAT_PREFIX,
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
    get_lowest_index,
    parse_chat_message,
    parse_logline,
    remove_ranks,
    strip_until,
    words_match,
)


@pytest.mark.parametrize(
    "rank_string, name_string",
    (
        ("Player1", "Player1"),
        ("[MVP++] Player1", "Player1"),
        ("[MVP+] Player1", "Player1"),
        ("[MVP] Player1", "Player1"),
        ("[VIP+] Player1", "Player1"),
        ("[VIP] Player1", "Player1"),
        ("[MOD] Player1", "Player1"),
        ("[OWNER] Player1", "Player1"),
        ("[MVP++] Player1 [VIP+] Player2", "Player1 Player2"),
        ("[MVP++] Player1, [VIP+] Player2", "Player1, Player2"),
        ("[MVP++] Player1 has joined the party!", "Player1 has joined the party!"),
        (
            "Joined [MVP++] Player1's party - joining Player2 and [VIP] Player3",
            "Joined Player1's party - joining Player2 and Player3",
        ),
        # Weird accepted cases
        ("[+ANYTHINGREALLY+++] Player1", "Player1"),
        ("[mixedCASE+] Player1", "Player1"),
        ("[+] Player1", "Player1"),
        # Cases where rank is not removed
        ("[numbers1234] Player1", "[numbers1234] Player1"),
        ("[special+&?] Player1", "[special+&?] Player1"),
        ("[] Player1", "[] Player1"),  # Empty brackets
        ("[VIP]Player1", "[VIP]Player1"),  # Missing space
        ("VIP Player1", "VIP Player1"),  # Missing brackets
    ),
)
def test_remove_ranks(rank_string: str, name_string: str) -> None:
    """Assert that remove_ranks functions properly"""
    assert remove_ranks(rank_string) == name_string


@pytest.mark.parametrize(
    "source, substrings, result",
    (
        ("a b c d", ("b", "f"), "b"),
        ("a b c d", ("b", "a"), "a"),
        ("a b c d", ("e", "f"), None),
        (
            "[CHAT1] MaliciousPlayer: [CHAT2] payload",
            ("[CHAT1] ", "[CHAT2] "),
            "[CHAT1] ",
        ),
        ("a b c d", (), None),
    ),
)
def test_get_lowest_index(source: str, substrings: tuple[str], result: str) -> None:
    assert get_lowest_index(source, *substrings) == result


@pytest.mark.parametrize(
    "line, until, suffix",
    (
        ("prefix: output", "prefix:", "output"),
        ("somejunk - prefix: output", "prefix:", "output"),
        ("somejunk - prefix:", "prefix:", ""),
        ("somejunk - prefix:   output      ", "prefix:", "output"),
        ("somejunk - prefix:   output      ", "prefix", ":   output"),
        ("CHAT MESSAGE: my message", "CHAT MESSAGE: ", "my message"),
        ("INCOMING CHAT MESSAGE: my message", "CHAT MESSAGE: ", "my message"),
        ("INCOMING CHAT MESSAGE: my message", "CHAT MESSAGE:", "my message"),
        ("INCOMING CHAT MESSAGE: my message", "CHAT ", "MESSAGE: my message"),
        # Test that players can't send chat messages that appear to come from the server
        (f"{CHAT_PREFIX} {CHAT_PREFIX} test", CHAT_PREFIX, f"{CHAT_PREFIX} test"),
        (
            "[Info: 2021-11-29 20:00:44.579410258: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] (Client thread) Info [CHAT] payload",
            CHAT_PREFIX,
            "(Client thread) Info [CHAT] payload",
        ),
    ),
)
def test_strip_until(line: str, until: str, suffix: str) -> None:
    """
    Assert that remove_ranks functions properly

    The function finds the first index of until and removes everything up to
    and including it. Also strips the result of whitespace on both ends.
    """
    assert strip_until(line, until=until) == suffix


@pytest.mark.parametrize(
    "words, target, full_match",
    (
        (("a", "list", "of", "words"), "a list of words", True),
        (("a", "long", "list", "of", "words"), "short list of words", False),
        (("a", "long", "list", "of", "words"), "a longish list of words", False),
        (("short", "list", "of", "words"), "a long list of words", False),
        (("short", "list", "of", "words"), "short list of words with suffix", False),
        (("list", "of", "words", "with", "suffix"), "list of words", False),
        (("word",), "word", True),
        (("",), "", True),
        ((" ",), " ", True),
        (("word", ""), "word ", True),
        (("word", " "), "word  ", True),
    ),
)
def test_words_match(words: Sequence[str], target: str, full_match: bool) -> None:
    """Assert that words_match functions properly"""
    assert words_match(words, target) == full_match


UNEVENTFUL_LOGLINES = (
    # Blank lines
    "[Info: 2021-11-29 20:00:44.579410258: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]                                      ",
    "[Info: 2021-11-29 20:00:52.346477397: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] "
    # Delimiter message
    "[Info: 2021-11-29 20:00:45.048717919: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] -----------------------------------------------------",
    "[Info: 2021-11-29 20:01:33.403385171: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
    # Leveling stuff
    "[Info: 2021-11-29 20:00:44.975806832: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You have 1 unclaimed leveling reward!",
    "[Info: 2021-11-29 20:00:44.975982283: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Click here to view it!",
    # Player joining lobby (not pre-game lobby)
    "[Info: 2021-11-29 20:00:45.654959105: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [MVP+] NotEnder joined the lobby!",
    "[Info: 2021-11-29 20:02:45.262785299: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]  >>> [MVP++] uhhlisuhh joined the lobby! <<<",
    # /g online
    "[Info: 2021-11-29 20:00:52.346336401: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Guild Name: GUILDNAME",
    "[Info: 2021-11-29 20:00:52.346582495: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]                                 -- Officer --",
    "[Info: 2021-11-29 20:00:52.346941141: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]                             -- Loyal Member --",
    "[Info: 2021-11-29 20:00:52.347251917: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]                                 -- Member --",
    "[Info: 2021-11-29 20:00:52.346732738: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [MVP+] Player1 ●  [MVP++] Player2 ●  ",
    "[Info: 2021-11-29 20:00:52.347593170: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Total Members: 120",
    "[Info: 2021-11-29 20:00:52.347689171: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Online Members: 5",
    "[Info: 2021-11-29 20:00:52.347842851: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Offline Members: 115",
    "[Info: 2021-11-29 20:00:52.347951536: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] -----------------------------------------------------",
    # Sumo duel
    "[Info: 2021-11-29 20:03:00.538297442: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You accepted [MVP++] Player1's Duel request!",
    "[Info: 2021-11-29 20:01:33.403523512: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]                                  Sumo Duel",
    "[Info: 2021-11-29 20:01:33.403683273: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]                      Eliminate your opponents!",
    "[Info: 2021-11-29 20:01:33.403841361: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]                            Opponent: Player1",
    # Kill
    "[Info: 2021-11-29 20:01:37.387390783: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Player2 was killed by Player1."
    # Chat messages
    "[Info: 2021-11-29 20:03:05.086918988: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Player1: hey",
    "[Info: 2021-11-29 20:01:02.198028928: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Guild > Player1 [MEM]: hello",
    "[Info: 2021-11-29 20:01:02.198028928: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Party > Player1 [MEM]: hello",
    "[Info: 2021-11-29 20:01:37.599407350: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [SPECTATOR] ✫ Sumo Rookie V sapporoV: gg",
    "[Info: 2021-11-29 20:01:37.599526846: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [GAME] Skydeaf: gg",
    "[Info: 2021-11-29 20:18:14.961703702: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [SHOUT] [RED] [VIP+] Player1: some chat message",
    # Game starting soon
    "[Info: 2021-11-29 20:01:28.418898025: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] The game starts in 5 seconds!",
    # Private game
    "[Info: 2021-11-29 20:09:06.079904026: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [MVP++] Player1 enabled Private Game",
    "[Info: 2021-11-29 20:09:09.809805686: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [MVP++] Player1 disabled Private Game",
    # In game stuff
    "[Info: 2021-11-29 20:11:16.397483792: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You purchased Wool",
    "[Info: 2021-11-29 20:11:16.470242031: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You don't have enough Iron! Need 4 more!",
    "[Info: 2021-11-29 20:11:36.117500057: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Player1 was filled full of lead by Player2.",
    "[Info: 2021-11-29 20:11:38.221423109: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You will respawn in 5 seconds!",
    # Mystery box
    "[Info: 2021-11-29 20:15:17.705912418: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] ✦ You found a ✰✰✰✰✰ Mystery Box!",
    # Internals
    "[Info: 2021-11-29 19:58:22.546643684: NetQueue.cpp(575)] NetQueue: worker thread started.",
    "[Info: 2021-11-29 19:58:22.546656499: mainLinux.cpp(250)] Running launcher bootstrap (version 1035)",
    "[Info: 2021-11-29 19:58:22.548908424: Common.cpp(32)] Native Launcher Version: 1035",
    # Bedwarspractice server
    "[Info: 2021-12-15 00:32:27.188867032: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Connecting to bwp-game-25...",
    "[Info: 2021-12-15 00:32:27.239004940: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Moving you to game server!",
    "[Info: 2021-12-15 00:32:27.239041920: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Successfully connected to bwp-game-25",
    "[Info: 2021-12-15 00:32:27.310287008: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Still waiting for other players. Attempt 1/10",
    "[Info: 2021-12-15 00:32:27.310298640: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You have joined with a new game! UUID: 5183e38b-e87b-410f-940e-dd259b3fc43f",
    "[Info: 2021-12-15 00:32:27.310308869: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Still waiting for other players. Attempt 1/10",
    "[Info: 2021-12-15 00:32:27.310318067: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Loading map...",
    "[Info: 2021-12-15 00:32:27.364797029: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] =================================",
    "[Info: 2021-12-15 00:32:27.364861521: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]                  Void Fight",
    "[Info: 2021-12-15 00:32:27.364880247: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]     Break the bed on the over side",
    "[Info: 2021-12-15 00:32:27.364895165: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]               to win the game!",
    "[Info: 2021-12-15 00:32:27.364918058: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] =================================",
    "[Info: 2021-12-15 00:32:27.554651901: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Players in this game: Player1 Player2 Player3 Player4 ",
    "[Info: 2021-12-15 00:32:27.554735369: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Game starting in 5 seconds!",
    # Near misses - messages that almost parse
    "[Info: 2021-11-29 20:01:23.997291428: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Player1 have joining (1/2)! has joined (",  # Malformed
    "[Info: 2021-11-29 20:01:23.997291428: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Player1 has joined (x/y)!",  # Malformed player count
    "[Info: 2021-11-29 20:09:47.192349993: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Player1 have quitting! has quit!",  # Malformed
    "[Info: 2021-11-29 20:08:49.380880233: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You have joined [MVP++] Player1 party!",  # No apostrophe
    "[Info: 2021-11-29 20:08:53.706306034: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [MVP+] Player2 joining theeee party? joined the party.",  # Malformed
    "[Info: 2021-11-29 22:16:47.779503684: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [VIP] Player1 have leaving thee party? has left the party.",  # Malformed
    "[Info: 2021-11-29 22:28:52.033936996: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] The party was transferred to someone",  # Too short
    "[Info: 2021-11-29 22:28:52.033936996: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] The party was transferred to Player2 notbecause [MVP++] Player1 didntleave",  # Malformed
    "[Info: 2021-12-06 22:23:29.795361404: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [MVP++] Player2 having disbanding has disbanded the party!",  # Malformed
    "[Info: 2021-12-09 00:21:25.792896760: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [VIP+] Player1 having removing from partying has been removed from the party.",  # Malformed
    "[Info: 2021-12-09 00:21:30.953440842: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Kicked [VIP] Player1 because they were offline.becausing offlining ",  # Malformed
    "[Info: 2021-12-10 00:57:30.104719428: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]  because they were offline.",  # Malformed
    "[Info: 2021-12-09 00:21:30.953440842: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [MVP+] Player1 wasing removing was removed from the party because they disconnected",  # Malformed
    "[Info: 2022-01-07 13:48:02.379053772: GameCallbacks.cpp(162)] Game/avt (Client thread) Info [CHAT] Your new API key is deadbeef-ae10-4d07-25f6-f23130b92652 justkidding",  # Malformed
    "[15:03:53] [Client thread/INFO]: [CHAT] You are now nicked as AmazingNick! just kidding",  # Malformed
    "[15:03:53] [Client thread/INFO]: [CHAT] You are now nicked as AmazingNick",  # Malformed (no !)
    "[15:03:53] [Client thread/INFO]: [CHAT] Can't find a player by the name of !someusername'",  # Missing '
    "[15:03:53] [Client thread/INFO]: [CHAT] Can't find a player by the name of '!someusername",  # Missing '
    "[15:03:53] [Client thread/INFO]: [CHAT] Can't find a player by the name of !someusername",  # Missing '
    "[15:03:53] [Client thread/INFO]: [CHAT] Can't find a player by the name of !someusername",  # Missing '
    "[15:03:53] [Client thread/INFO]: [CHAT] Can't find a player by the name of '!somewierdcommand'",  # Unknown command
    "[15:03:53] [Client thread/INFO]: [CHAT] Can't find a player by the name of '!",  # Empty/malformed
    "[15:03:53] [Client thread/INFO]: [CHAT] Can't find a player by the name of '!a=b=c'",  # Too many arguments to setnick
    # Attempts to inject log messages
    "[15:03:53] [Client thread/INFO]: [CHAT] [MVP+] MaliciousPlayer: (Client thread) Info Setting user: Player1",
    "[15:03:53] [Client thread/INFO]: [CHAT] [MVP+] MaliciousPlayer: (Client thread) Info [CHAT] ONLINE: Player1",
    "[Info: 2021-11-29 22:30:40.455294561: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] MaliciousPlayer: [15:03:32] [ForkJoinPool.commonPool-worker-3/INFO]: [LC] Setting user: MaliciousPlayer",
    "[Info: 2021-11-29 22:30:40.455294561: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] MaliciousPlayer: [15:03:53] [Client thread/INFO]: [CHAT] ONLINE: Player1",
)


parsing_test_cases = (
    *[(line, None) for line in UNEVENTFUL_LOGLINES],
    (
        # Initialize as on vanilla
        "[Info: 2022-01-07 13:42:07.884914205: GameCallbacks.cpp(162)] Game/ave (Client thread) Info Setting user: Player1",
        InitializeAsEvent("Player1"),
    ),
    (
        # Initialize as on forge
        "[Info: 2021-11-29 23:26:26.372869411: GameCallbacks.cpp(162)] Game/net.minecraft.client.Minecraft (Client thread) Info Setting user: Player1",
        InitializeAsEvent("Player1"),
    ),
    (
        # Initialize as on lunar
        "[15:03:32] [ForkJoinPool.commonPool-worker-3/INFO]: [LC] Setting user: Player1",
        InitializeAsEvent("Player1"),
    ),
    (
        "[Info: 2021-11-29 22:30:40.455294561: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] ONLINE: Player1, Player2, Player3, Player5, Player6, Player7, Player8, Player9",
        LobbyListEvent(
            usernames=[
                "Player1",
                "Player2",
                "Player3",
                "Player5",
                "Player6",
                "Player7",
                "Player8",
                "Player9",
            ]
        ),
    ),
    (
        # Nick reuse on lunar client
        "[15:03:53] [Client thread/INFO]: [CHAT] You are now nicked as AmazingNick!",
        NewNicknameEvent(nick="AmazingNick"),
    ),
    (
        # Lobby list on lunar client
        "[15:03:53] [Client thread/INFO]: [CHAT] ONLINE: Player1",
        LobbyListEvent(usernames=["Player1"]),
    ),
    (
        # Lobby swap on vanilla
        "[Info: 2022-01-07 13:44:01.231411580: GameCallbacks.cpp(162)] Game/avt (Client thread) Info [CHAT] Sending you to mini733G!",
        LobbySwapEvent(),
    ),
    (
        "[Info: 2021-11-29 20:01:23.792072597: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Sending you to mini1145V!",
        LobbySwapEvent(),
    ),
    (
        "[Info: 2021-12-27 13:32:29.420302635: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You were sent to a lobby because someone in your party left!",
        LobbySwapEvent(),
    ),
    (
        "[Info: 2021-11-29 20:01:23.997291428: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Player1 has joined (1/2)!",
        LobbyJoinEvent(username="Player1", player_count=1, player_cap=2),
    ),
    (
        "[Info: 2021-11-29 20:01:24.386456858: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Player2 has joined (2/16)!",
        LobbyJoinEvent(username="Player2", player_count=2, player_cap=16),
    ),
    (
        "[Info: 2021-11-29 20:09:47.192349993: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Player1 has quit!",
        LobbyLeaveEvent(username="Player1"),
    ),
    (
        "[Info: 2021-11-29 23:13:35.658182633: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You left the party.",
        PartyDetachEvent(),
    ),
    (
        "[Info: 2021-11-29 20:08:40.030141221: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You are not currently in a party.",
        PartyDetachEvent(),
    ),
    (
        "[Info: 2021-12-06 22:23:29.795361404: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [MVP++] Player2 has disbanded the party!",
        PartyDetachEvent(),
    ),
    (
        "[Info: 2021-12-06 22:23:29.795361404: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You have been kicked from the party by [MVP+] Player1",
        PartyDetachEvent(),
    ),
    (
        "[Info: 2021-12-31 12:24:43.921980855: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] The party was disbanded because all invites expired and the party was empty",
        PartyDetachEvent(),
    ),
    (
        "[Info: 2021-11-29 20:08:49.380880233: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You have joined [MVP++] Player1's party!",
        PartyAttachEvent(username="Player1"),
    ),
    (
        "[Info: 2021-12-06 20:38:05.407568857: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You'll be partying with: Player2, [MVP++] Player3, [MVP+] Player4, [MVP+] Player5",
        PartyJoinEvent(usernames=["Player2", "Player3", "Player4", "Player5"]),
    ),
    (
        "[Info: 2021-11-29 20:08:53.706306034: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [MVP+] Player2 joined the party.",
        PartyJoinEvent(usernames=["Player2"]),
    ),
    (
        "[Info: 2021-11-29 22:16:47.779503684: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [VIP] Player1 has left the party.",
        PartyLeaveEvent(usernames=["Player1"]),
    ),
    (
        "[Info: 2021-11-29 22:28:52.033936996: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] The party was transferred to Player2 because [MVP++] Player1 left",
        PartyLeaveEvent(usernames=["Player1"]),
    ),
    (
        "[Info: 2021-12-09 00:21:25.792896760: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [VIP+] Player1 has been removed from the party.",
        PartyLeaveEvent(usernames=["Player1"]),
    ),
    (
        "[Info: 2021-12-09 00:21:30.953440842: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Kicked [VIP] Player1 because they were offline.",
        PartyLeaveEvent(usernames=["Player1"]),
    ),
    (
        "[Info: 2021-12-09 00:21:30.953440842: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [MVP+] Player1 was removed from the party because they disconnected",
        PartyLeaveEvent(usernames=["Player1"]),
    ),
    (
        "[Info: 2021-12-10 00:57:30.104719428: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Kicked [MVP++] Player1, [MVP+] Player2 because they were offline.",
        PartyLeaveEvent(usernames=["Player1", "Player2"]),
    ),
    (
        "[Info: 2021-11-29 22:17:40.417692543: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Party Members (3)",
        PartyListIncomingEvent(),
    ),
    (
        "[Info: 2021-11-29 22:17:40.417791980: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Party Leader: [MVP++] Player1 ●",
        PartyMembershipListEvent(usernames=["Player1"], role="leader"),
    ),
    (
        "[Info: 2021-11-29 22:17:40.417869567: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Party Moderators: Player2 ● [MVP+] Player3 ● ",
        PartyMembershipListEvent(usernames=["Player2", "Player3"], role="moderators"),
    ),
    (
        "[Info: 2021-11-29 22:17:40.417869567: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Party Members: Player2 ● [MVP+] Player3 ● ",
        PartyMembershipListEvent(usernames=["Player2", "Player3"], role="members"),
    ),
    (
        "[Info: 2021-12-21 19:10:39.757655172: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]                                   Bed Wars",
        StartBedwarsGameEvent(),
    ),
    (
        "[Info: 2022-01-08 17:27:38.908122114: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT]                     1st Killer - [MVP+] Player1 - 8",
        EndBedwarsGameEvent(),
    ),
    (
        "[Info: 2022-01-07 13:48:02.379053772: GameCallbacks.cpp(162)] Game/avt (Client thread) Info [CHAT] Your new API key is deadbeef-ae10-4d07-25f6-f23130b92652",
        NewAPIKeyEvent("deadbeef-ae10-4d07-25f6-f23130b92652"),
    ),
    (
        "[Info: 2022-05-06 20:41:58.104577043: GameCallbacks.cpp(177)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Can't find a player by the name of '!nick=username'",
        WhisperCommandSetNickEvent(nick="nick", username="username"),
    ),
    (
        "[Info: 2022-05-06 20:41:58.104577043: GameCallbacks.cpp(177)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Can't find a player by the name of '!nick='",
        WhisperCommandSetNickEvent(nick="nick", username=None),
    ),
)


parsing_test_ids = [
    f"{strip_until(test_case[0], until=CHAT_PREFIX)}-{type(test_case[1]).__name__}"
    for test_case in parsing_test_cases
]


@pytest.mark.parametrize("logline, event", parsing_test_cases, ids=parsing_test_ids)
def test_parsing(logline: str, event: Event) -> None:
    """Assert that the correct events are returned from parse_logline"""
    assert parse_logline(logline) == event
