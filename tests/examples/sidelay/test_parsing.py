# Too many long lines in this file
# flake8: noqa
import pytest

from examples.sidelay.parsing import (
    CHAT_PREFIX,
    Event,
    InitializeAsEvent,
    LobbyJoinEvent,
    LobbyLeaveEvent,
    LobbyListEvent,
    PartyAttachEvent,
    PartyDetachEvent,
    PartyJoinEvent,
    PartyLeaveEvent,
    PartyListIncomingEvent,
    PartyMembershipListEvent,
    parse_chat_message,
    parse_logline,
    remove_ranks,
    strip_until,
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
        ("[+] Player1", "Player1"),  # Empty brackets
        # Cases where content in brackets is not recognized as a rank
        ("[numbers1234] Player1", "[numbers1234] Player1"),
        ("[special+&?] Player1", "[special+&?] Player1"),
        ("[] Player1", "[] Player1"),  # Empty brackets
        ("[VIP]Player1", "[VIP]Player1"),  # Missing space
    ),
)
def test_remove_ranks(rank_string: str, name_string: str) -> None:
    """Assert that remove_ranks functions properly"""
    assert remove_ranks(rank_string) == name_string


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
    ),
)
def test_strip_until(line: str, until: str, suffix: str) -> None:
    """
    Assert that remove_ranks functions properly

    The function finds the first index of until and removes everything up to
    and including it. Also strips the result of whitespace on both ends.
    """
    assert strip_until(line, until=until) == suffix


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
    # Joining a minigame
    "[Info: 2021-11-29 20:01:23.792072597: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Sending you to mini1145V!",
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
    # Near misses - messages that almost parse
    "[Info: 2021-11-29 20:01:23.997291428: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Player1 have joining (1/2)! has joined (",  # Malformed
    "[Info: 2021-11-29 20:01:23.997291428: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Player1 has joined (x/y)!",  # Malformed player count
    "[Info: 2021-11-29 20:09:47.192349993: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] Player1 have quitting! has quit!",  # Malformed
    "[Info: 2021-11-29 20:08:49.380880233: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You have joined [MVP++] Player1 party!",  # No apostrophe
    "[Info: 2021-11-29 20:08:53.706306034: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [MVP+] Player2 joining theeee party? joined the party.",  # Malformed
    "[Info: 2021-11-29 22:16:47.779503684: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [VIP] Player1 have leaving thee party? has left the party.",  # Malformed
    "[Info: 2021-11-29 22:28:52.033936996: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] The party was transferred to someone",  # Too short
    "[Info: 2021-11-29 22:28:52.033936996: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] The party was transferred to Player2 notbecause [MVP++] Player1 didntleave",  # Malformed
)


parsing_test_cases = (
    *[(line, None) for line in UNEVENTFUL_LOGLINES],
    (
        "[Info: 2021-11-29 23:26:26.372869411: GameCallbacks.cpp(162)] Game/net.minecraft.client.Minecraft (Client thread) Info Setting user: Player1",
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
        "[Info: 2021-11-29 20:08:49.380880233: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] You have joined [MVP++] Player1's party!",
        PartyAttachEvent(usernames=["Player1"]),
    ),
    (
        "[Info: 2021-11-29 20:08:53.706306034: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [MVP+] Player2 joined the party.",
        PartyJoinEvent(username="Player2"),
    ),
    (
        "[Info: 2021-11-29 22:16:47.779503684: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] [VIP] Player1 has left the party.",
        PartyLeaveEvent(username="Player1"),
    ),
    (
        "[Info: 2021-11-29 22:28:52.033936996: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] The party was transferred to Player2 because [MVP++] Player1 left",
        PartyLeaveEvent(username="Player1"),
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
)


@pytest.mark.parametrize("logline, event", parsing_test_cases)
def test_parsing(logline: str, event: Event) -> None:
    """Assert that the correct events are returned from parse_logline"""
    assert parse_logline(logline) == event

    if CHAT_PREFIX in logline:
        chat_message = strip_until(logline, until=CHAT_PREFIX)
        assert parse_chat_message(chat_message) == event
