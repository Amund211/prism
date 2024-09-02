import unittest.mock
from collections.abc import Iterable
from typing import Final

import pytest

from prism.overlay.events import (
    BedwarsDisconnectEvent,
    BedwarsFinalKillEvent,
    BedwarsGameStartingSoonEvent,
    BedwarsReconnectEvent,
    ChatMessageEvent,
    EndBedwarsGameEvent,
    Event,
    InitializeAsEvent,
    LobbyJoinEvent,
    LobbyLeaveEvent,
    LobbyListEvent,
    LobbySwapEvent,
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
from prism.overlay.process_event import (
    fast_forward_state,
    process_event,
    process_loglines,
)
from tests.prism.overlay.utils import OWN_USERNAME, MockedController, create_state

process_event_test_cases_base: tuple[
    tuple[str, MockedController, Event, MockedController, bool], ...
] = (
    (
        "initialize",
        MockedController(state=create_state(own_username=None)),
        InitializeAsEvent("NewPlayer"),
        MockedController(state=create_state(own_username="NewPlayer")),
        True,
    ),
    (
        "re-initialize",
        MockedController(
            state=create_state(
                party_members={"OwnUsername", "Player1"},
                lobby_players={"OwnUsername", "Player1"},
                alive_players={"Player1"},
                out_of_sync=True,
                in_queue=True,
            )
        ),
        InitializeAsEvent("NewPlayer"),
        MockedController(state=create_state(own_username="NewPlayer")),
        True,
    ),
    (
        "swap lobby",
        MockedController(
            wants_shown=True,
            state=create_state(
                party_members={"OwnUsername", "Player2"}, lobby_players={"RandomPlayer"}
            ),
        ),
        LobbySwapEvent(),
        MockedController(
            wants_shown=None,
            state=create_state(party_members={"OwnUsername", "Player2"}),
        ),
        True,
    ),
    (
        "lobby join solo",
        MockedController(wants_shown=True),
        LobbyJoinEvent("Player1", player_count=1, player_cap=8),
        MockedController(state=create_state(lobby_players={"Player1"}, in_queue=True)),
        True,
    ),
    (
        "lobby join doubles/fours",
        MockedController(wants_shown=False),
        LobbyJoinEvent("Player1", player_count=1, player_cap=16),
        MockedController(state=create_state(lobby_players={"Player1"}, in_queue=True)),
        True,
    ),
    (
        "lobby leave",
        MockedController(state=create_state(lobby_players={"Leaving"}, in_queue=True)),
        LobbyLeaveEvent("Leaving"),
        MockedController(state=create_state(in_queue=True)),
        True,
    ),
    (
        "lobby leave out of queue",
        MockedController(
            wants_shown=True, state=create_state(lobby_players={"Leaving"})
        ),
        LobbyLeaveEvent("Leaving"),
        MockedController(state=create_state(in_queue=True)),
        True,
    ),
    (
        "chat message in queue",
        MockedController(state=create_state(in_queue=True)),
        ChatMessageEvent(username="Player1", message="Hello!"),
        MockedController(state=create_state(in_queue=True, lobby_players={"Player1"})),
        True,
    ),
    (
        "chat message out of queue",
        MockedController(state=create_state(in_queue=False)),
        ChatMessageEvent(username="Player1", message="Hello!"),
        MockedController(state=create_state(in_queue=False)),
        False,
    ),
    (
        "lobby list out of queue",
        MockedController(
            state=create_state(lobby_players={"PersonFromLastLobby"}, in_queue=False)
        ),
        LobbyListEvent([OWN_USERNAME, "Player1", "Player2"]),
        MockedController(
            state=create_state(
                lobby_players={OWN_USERNAME, "Player1", "Player2"}, in_queue=False
            ),
            wants_shown=True,
        ),
        True,
    ),
    (
        # NOTE: Not a valid test case any more since /who no longer works in queue
        "lobby list in queue",
        MockedController(
            state=create_state(lobby_players={"PersonFromLastLobby"}, in_queue=True),
            wants_shown=False,
        ),  # Old members cleared
        LobbyListEvent([OWN_USERNAME, "Player1", "Player2"]),
        MockedController(
            state=create_state(
                lobby_players={OWN_USERNAME, "Player1", "Player2"}, in_queue=True
            ),
            wants_shown=True,
        ),
        True,
    ),
    (
        "lobby list early in game",
        MockedController(
            state=create_state(
                lobby_players={"PersonFromLastLobby"}, last_game_start=10
            ),
            wants_shown=None,
        ),  # Old members cleared
        LobbyListEvent([OWN_USERNAME, "Player1", "Player2"]),
        MockedController(
            state=create_state(
                lobby_players={OWN_USERNAME, "Player1", "Player2"},
                last_game_start=10,
                now_func=lambda: 11,
            ),
            wants_shown=None,
        ),
        True,
    ),
    (
        "lobby list late in game",
        MockedController(
            state=create_state(
                lobby_players={"PersonFromLastLobby"},
                last_game_start=10,
                now_func=lambda: 30,
            ),
            wants_shown=None,
        ),  # Old members cleared
        LobbyListEvent([OWN_USERNAME, "Player1", "Player2"]),
        MockedController(
            state=create_state(
                lobby_players={OWN_USERNAME, "Player1", "Player2"},
                last_game_start=10,
            ),
            wants_shown=True,
        ),
        True,
    ),
    (
        "party attach",
        MockedController(),
        PartyAttachEvent("Player2"),
        MockedController(state=create_state(party_members={"OwnUsername", "Player2"})),
        True,
    ),
    (
        "party detach",
        MockedController(state=create_state(party_members={"OwnUsername", "Player2"})),
        PartyDetachEvent(),
        MockedController(),
        True,
    ),
    (
        "party join multiple",
        MockedController(state=create_state(party_members={"OwnUsername", "Player2"})),
        PartyJoinEvent(["Player3", "Player4"]),
        MockedController(
            state=create_state(
                party_members={"OwnUsername", "Player2", "Player3", "Player4"}
            )
        ),
        True,
    ),
    (
        "party leave",
        MockedController(
            state=create_state(party_members={"OwnUsername", "Player2", "Player3"})
        ),
        PartyLeaveEvent(["Player3"]),
        MockedController(state=create_state(party_members={"OwnUsername", "Player2"})),
        True,
    ),
    (
        "party leave multiple",
        MockedController(
            state=create_state(party_members={"OwnUsername", "Player2", "Player3"})
        ),
        PartyLeaveEvent(["Player3", "Player2"]),
        MockedController(state=create_state(party_members={"OwnUsername"})),
        True,
    ),
    (
        "party list incoming",
        MockedController(
            state=create_state(party_members={"OwnUsername", "Player2", "Player3"})
        ),
        PartyListIncomingEvent(),
        MockedController(),
        False,
    ),
    (
        "party list moderators",
        MockedController(state=create_state(party_members={"OwnUsername"})),
        PartyMembershipListEvent(usernames=["Player1", "Player2"], role="moderators"),
        MockedController(
            state=create_state(party_members={"Player1", "Player2", "OwnUsername"})
        ),
        True,
    ),
    (
        "bedwars game starting soon",
        MockedController(),
        BedwarsGameStartingSoonEvent(seconds=5),
        MockedController(),
        False,  # No need to redraw the screen - only show the overlay
    ),
    (
        "bedwars game starting soon, already in queue",
        MockedController(state=create_state(in_queue=True)),
        BedwarsGameStartingSoonEvent(seconds=4),
        MockedController(state=create_state(in_queue=True)),
        False,  # No need to redraw the screen - only show the overlay
    ),
    (
        "start bedwars game",
        MockedController(
            wants_shown=False, state=create_state(in_queue=True, now_func=lambda: 1234)
        ),
        StartBedwarsGameEvent(),
        MockedController(
            wants_shown=None,
            state=create_state(in_queue=False, out_of_sync=True, last_game_start=1234),
        ),
        False,  # No need to redraw the screen - only hide the overlay
    ),
    (
        "final kill",
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"},
                alive_players={"Player1", "Player2"},
            )
        ),
        BedwarsFinalKillEvent(
            dead_player="Player1",
            raw_message="Player1 was killed by Player2. FINAL KILL!",
        ),
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        True,
    ),
    (
        "final kill on already dead player",
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        BedwarsFinalKillEvent(
            dead_player="Player1",
            raw_message="Player1 was killed by Player2. FINAL KILL!",
        ),
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        True,  # TODO: Could be False
    ),
    (
        "disconnect",
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"},
                alive_players={"Player1", "Player2"},
            )
        ),
        BedwarsDisconnectEvent(username="Player1"),
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        True,
    ),
    (
        "disconnect while not alive",
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        BedwarsDisconnectEvent(username="Player1"),
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        True,  # TODO: Could be False
    ),
    (
        "disconnect while not in lobby",
        MockedController(
            state=create_state(lobby_players={"Player2"}, alive_players={"Player2"})
        ),
        BedwarsDisconnectEvent(username="Player1"),
        MockedController(
            state=create_state(lobby_players={"Player2"}, alive_players={"Player2"})
        ),
        True,  # TODO: Could be False
    ),
    (
        "disconnect while not in lobby, but alive somehow",
        MockedController(
            state=create_state(
                lobby_players={"Player2"}, alive_players={"Player1", "Player2"}
            )
        ),
        BedwarsDisconnectEvent(username="Player1"),
        MockedController(
            state=create_state(lobby_players={"Player2"}, alive_players={"Player2"})
        ),
        True,
    ),
    (
        "reconnect",
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        BedwarsReconnectEvent(username="Player1"),
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"},
                alive_players={"Player1", "Player2"},
            )
        ),
        True,
    ),
    (
        "disconnect while alive",
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        BedwarsReconnectEvent(username="Player2"),
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        True,  # TODO: Could be False
    ),
    (
        "reconnect while not in lobby",
        MockedController(
            state=create_state(lobby_players={"Player2"}, alive_players={"Player2"})
        ),
        BedwarsReconnectEvent(username="Player1"),
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"},
                alive_players={"Player1", "Player2"},
            )
        ),
        True,
    ),
    (
        "reconnect while not in lobby, but alive somehow",
        MockedController(
            state=create_state(
                lobby_players={"Player2"}, alive_players={"Player1", "Player2"}
            )
        ),
        BedwarsReconnectEvent(username="Player1"),
        MockedController(
            state=create_state(
                lobby_players={"Player1", "Player2"},
                alive_players={"Player1", "Player2"},
            )
        ),
        True,
    ),
    (
        "end bedwars game",
        MockedController(
            state=create_state(lobby_players={"a", "bunch", "of", "players"})
        ),
        EndBedwarsGameEvent(),
        MockedController(update_presence_event_set=True),
        True,
    ),
    # Special cases
    (
        # New nickname when own username is unknown
        "new nickname unknown username",
        MockedController(state=create_state(own_username=None)),
        NewNicknameEvent("AmazingNick"),
        MockedController(state=create_state(own_username=None)),
        False,
    ),
    (
        # Party leave when own username is unknown
        "party leave unknown username",
        MockedController(
            state=create_state(party_members={"Player1", "Player2"}, own_username=None)
        ),
        PartyDetachEvent(),
        MockedController(state=create_state(own_username=None)),
        True,
    ),
    (
        # Lobby swap when own username is unknown
        "lobby swap unknown username",
        MockedController(
            wants_shown=False,
            state=create_state(lobby_players={"Player1", "Player2"}, own_username=None),
        ),
        LobbySwapEvent(),
        MockedController(wants_shown=None, state=create_state(own_username=None)),
        True,
    ),
    (
        # Player not in party leaves party
        "player not in party leaves party",
        MockedController(state=create_state(party_members={"OwnUsername", "Player2"})),
        PartyLeaveEvent(["RandomPlayer"]),
        MockedController(state=create_state(party_members={"OwnUsername", "Player2"})),
        # TODO: False,
        True,
    ),
    (
        # Player not in lobby leaves lobby
        "player not in lobby leaves lobby",
        MockedController(
            state=create_state(in_queue=True, lobby_players={"Player1", "Player2"})
        ),
        LobbyLeaveEvent("RandomPlayer"),
        MockedController(
            state=create_state(in_queue=True, lobby_players={"Player1", "Player2"})
        ),
        # TODO: False,
        True,
    ),
    (
        "final kill on player not in lobby",
        MockedController(state=create_state(lobby_players={"Player2"})),
        BedwarsFinalKillEvent(
            dead_player="Player1",
            raw_message="Player1 was killed by Player2. FINAL KILL!",
        ),
        MockedController(state=create_state(lobby_players={"Player2"})),
        True,  # TODO: Could be False
    ),
    (
        "final kill on player not in lobby, but alive somehow",
        MockedController(
            state=create_state(
                lobby_players={"Player2"}, alive_players={"Player1", "Player2"}
            )
        ),
        BedwarsFinalKillEvent(
            dead_player="Player1",
            raw_message="Player1 was killed by Player2. FINAL KILL!",
        ),
        MockedController(
            state=create_state(lobby_players={"Player2"}, alive_players={"Player2"})
        ),
        True,
    ),
    (
        # Small player cap -> not bedwars
        "player join non bedwars",
        MockedController(),
        LobbyJoinEvent("Player1", player_count=2, player_cap=2),
        MockedController(),
        False,
    ),
    (
        # Player count too low -> out of sync
        "too few known players in lobby",
        MockedController(),
        LobbyJoinEvent("Player1", player_count=5, player_cap=16),
        MockedController(
            state=create_state(
                lobby_players={"Player1"}, out_of_sync=True, in_queue=True
            )
        ),
        True,
    ),
    (
        # Player count too high -> clear lobby
        "too many known players in lobby",
        MockedController(
            state=create_state(lobby_players={"PlayerA", "PlayerB"}, in_queue=True)
        ),
        LobbyJoinEvent("Player1", player_count=1, player_cap=16),
        MockedController(state=create_state(lobby_players={"Player1"}, in_queue=True)),
        True,
    ),
    (
        # Player count too high -> clear lobby, still out of sync
        "too many known players in lobby, too few remaining",
        MockedController(
            state=create_state(
                lobby_players={"PlayerA", "PlayerB", "PlayerC"}, in_queue=True
            )
        ),
        LobbyJoinEvent("Player1", player_count=3, player_cap=16),
        MockedController(
            state=create_state(
                lobby_players={"Player1"}, out_of_sync=True, in_queue=True
            )
        ),
        True,
    ),
    (
        "new queue with in-sync old lobby (weird)",
        MockedController(
            state=create_state(lobby_players={"PlayerA", "PlayerB"}, in_queue=False)
        ),
        LobbyJoinEvent("Player1", player_count=8, player_cap=16),
        MockedController(
            state=create_state(
                lobby_players={"PlayerA", "PlayerB", "Player1"},
                out_of_sync=True,
                in_queue=True,
            )
        ),
        True,
    ),
    (
        "new queue with lobby from previous game",
        MockedController(
            state=create_state(
                lobby_players={"PlayerA", "PlayerB"},
                alive_players={"PlayerB"},
                in_queue=False,
            )
        ),
        LobbyJoinEvent("Player1", player_count=8, player_cap=16),
        MockedController(
            state=create_state(
                lobby_players={"Player1"}, out_of_sync=True, in_queue=True
            )
        ),
        True,
    ),
    (
        "new queue with old lobby and too many players",
        MockedController(
            state=create_state(lobby_players={"PlayerA", "PlayerB"}, in_queue=False)
        ),
        LobbyJoinEvent("Player1", player_count=1, player_cap=16),
        MockedController(state=create_state(lobby_players={"Player1"}, in_queue=True)),
        True,
    ),
    (
        "don't remove yourself from the party",
        MockedController(state=create_state()),
        PartyLeaveEvent(["OwnUsername"]),
        MockedController(state=create_state()),
        True,
    ),
    (
        "clear the party when you leave",
        MockedController(
            state=create_state(party_members={"OwnUsername", "abc", "def"})
        ),
        PartyLeaveEvent(["OwnUsername"]),
        MockedController(state=create_state()),
        True,
    ),
    (
        "party leave with no own_username",
        MockedController(state=create_state(own_username=None)),
        PartyLeaveEvent(["OwnUsername"]),
        MockedController(state=create_state(own_username=None)),
        True,
    ),
)

process_event_test_ids = [test_case[0] for test_case in process_event_test_cases_base]
assert len(process_event_test_ids) == len(
    set(process_event_test_ids)
), "Test ids should be unique"

process_event_test_cases = [
    test_case[1:] for test_case in process_event_test_cases_base
]


@pytest.mark.parametrize(
    "initial_controller, event, target_controller, redraw",
    process_event_test_cases,
    ids=process_event_test_ids,
)
def test_process_event(
    initial_controller: MockedController,
    event: Event,
    target_controller: MockedController,
    redraw: bool,
) -> None:
    """Assert that process_event functions properly"""
    initial_controller.state, will_redraw = process_event(initial_controller, event)

    new_controller = initial_controller
    assert new_controller == target_controller
    assert new_controller.extra == target_controller.extra
    assert will_redraw == redraw


@pytest.mark.parametrize(
    "event",
    (
        NewNicknameEvent("AmazingNick"),
        WhisperCommandSetNickEvent(nick="AmazingNick", username="MyIGN"),
    ),
)
def test_process_event_set_nickname(event: Event) -> None:
    """Assert that set_nickname is called properly"""
    username = "MyIGN"
    nick = "AmazingNick"

    controller = MockedController(state=create_state(own_username=username))

    with unittest.mock.patch(
        "prism.overlay.process_event.set_nickname"
    ) as patched_set_nickname:
        new_state, will_redraw = process_event(controller, event)

    patched_set_nickname.assert_called_once_with(
        nick=nick, username=username, controller=controller
    )
    assert not will_redraw  # set_nickname sets redraw_flag


def test_process_event_autodenick_teammate() -> None:
    """
    Assert that autodenick_teammate is called when StartBedwarsGameEvent is received
    """
    controller = MockedController()

    with unittest.mock.patch(
        "prism.overlay.process_event.autodenick_teammate"
    ) as patched_autodenick_teammate:
        new_state, will_redraw = process_event(controller, StartBedwarsGameEvent())

    patched_autodenick_teammate.assert_called_once()
    assert not will_redraw


def test_process_event_bedwars_game_ended() -> None:
    """
    Assert that bedwars_game_ended is called when EndBedwarsGameEvent is received
    """
    controller = MockedController()

    with unittest.mock.patch(
        "prism.overlay.process_event.bedwars_game_ended"
    ) as patched_bedwars_game_ended:
        new_state, will_redraw = process_event(controller, EndBedwarsGameEvent())

    patched_bedwars_game_ended.assert_called_once()

    # The overlay will redraw after the lobby has been cleared, not causing any
    # additional stats requests due to the cache clear.
    assert will_redraw


CHAT = "[Info: 2021-11-29 22:17:40.417869567: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] "  # noqa: E501
INFO = "[Info: 2021-11-29 23:26:26.372869411: GameCallbacks.cpp(162)] Game/net.minecraft.client.Minecraft (Client thread) Info "  # noqa: E501

FAST_FORWARD_STATE_CASES: Final = (
    (
        MockedController(state=create_state(own_username=None)),
        (
            f"{INFO}Setting user: Me",
            f"{CHAT}Party Moderators: Player1 ● [MVP+] Player2 ● ",
            f"{CHAT}Player1 has joined (1/16)!",
            f"{CHAT}Player2 has joined (2/16)!",
            f"{CHAT}Me has joined (3/16)!",
            f"{CHAT}Someone has joined (4/16)!",
            f"{CHAT}[MVP+] Player1: hows ur day?",
        ),
        MockedController(
            state=create_state(
                own_username="Me",
                party_members={"Me", "Player1", "Player2"},
                lobby_players={"Me", "Player1", "Player2", "Someone"},
                in_queue=True,
            )
        ),
    ),
    (
        # Excerpt from new multiver lunar logfile
        MockedController(state=create_state(own_username=None)),
        (
            "[16:54:00] [Client thread/INFO]: Setting user: Player595",  # Strange
            "[16:54:00] [Client thread/INFO]: (Session ID is token:0:Player595)",
            "[16:54:12] [Client thread/INFO]: [LC Accounts] Loaded content for [YourIGN] Token IAT",  # noqa: E501
            "[16:54:12] [Client thread/INFO]: [LC Accounts] Starting Refreshing YourIGN with -4241459972ms till expired (Valid: false).",  # noqa: E501
            "[16:54:15] [Client thread/INFO]: [LC Accounts] Finishing Refreshing YourIGN (Valid: true).",  # noqa: E501
            "[16:54:15] [Client thread/INFO]: [LC Accounts] Logging into account YourIGN ",  # noqa: E501
            "[16:54:15] [Client thread/INFO]: [LC] Setting user: YourIGN",
            "[16:54:15] [Client thread/INFO]: [LC Accounts] Able to login YourIGN",
            "[16:54:17] [WebSocketConnectReadThread-73/INFO]: [LC Assets] Connection established as YourIGN",  # noqa: E501
            "[16:54:59] [Client thread/INFO]: Connecting to mc.hypixel.net, 25565",
            "[16:55:01] [Client thread/INFO]: [CHAT]                                      ",  # noqa: E501
            "[16:55:01] [Client thread/INFO]: [CHAT]                          ",
            "[16:55:01] [Client thread/INFO]: [CHAT] --------------  Guild: Message Of The Day  --------------",  # noqa: E501
        ),
        MockedController(state=create_state(own_username="YourIGN")),
    ),
    (
        # Ensure game starts in lucky blocks
        MockedController(
            state=create_state(
                now_func=lambda: 1.5,
                in_queue=True,
                lobby_players={
                    "OwnUsername",
                    "2",
                    "3",
                    "4",
                    "5",
                    "6",
                    "7",
                    "8",
                    "9",
                    "10",
                    "11",
                    "12",
                    "13",
                    "14",
                    "15",
                },
            )
        ),
        (
            "[16:12:39] [Client thread/INFO]: [CHAT] Player16 has joined (16/16)!",  # noqa: E501
            "[16:12:40] [Client thread/INFO]: [CHAT] ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            "[16:12:40] [Client thread/INFO]: [CHAT]                        Bed Wars Lucky Blocks",  # noqa: E501
            "[16:12:40] [Client thread/INFO]: [CHAT] ",
            "[16:12:40] [Client thread/INFO]: [CHAT]     Collect Lucky Blocks from resource generators",  # noqa: E501
            "[16:12:40] [Client thread/INFO]: [CHAT]        to receive random loot! Break them to reveal",  # noqa: E501
            "[16:12:40] [Client thread/INFO]: [CHAT]                              their contents!",  # noqa: E501
            "[16:12:40] [Client thread/INFO]: [CHAT] ",
            "[16:12:40] [Client thread/INFO]: [CHAT] ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
        ),
        MockedController(
            state=create_state(
                last_game_start=1.5,
                in_queue=False,
                out_of_sync=True,
                lobby_players={
                    "OwnUsername",
                    "2",
                    "3",
                    "4",
                    "5",
                    "6",
                    "7",
                    "8",
                    "9",
                    "10",
                    "11",
                    "12",
                    "13",
                    "14",
                    "15",
                    "Player16",
                },
            )
        ),
    ),
    (
        MockedController(state=create_state(own_username=None)),
        (
            f"{INFO}Setting user: Me",
            f"{CHAT}Party Moderators: Player1 ● [MVP+] Player2 ● ",
            f"{CHAT}Player1 has joined (1/12)!",
            f"{CHAT}Player2 has joined (2/12)!",
            f"{CHAT}Me has joined (3/12)!",
            f"{CHAT}Someone0 has joined (4/12)!",
            f"{CHAT}Someone1 has joined (5/12)!",
            f"{CHAT}Someone2 has joined (6/12)!",
            f"{CHAT}Someone3 has joined (7/12)!",
            f"{CHAT}Someone4 has joined (8/12)!",
            f"{CHAT}§7Someone1§7: any1 wanna party?",
            f"{CHAT}Someone5 has joined (9/12)!",
            f"{CHAT}Someone6 has joined (10/12)!",
            f"{CHAT}Someone7 has joined (11/12)!",
            f"{CHAT}Someone8 has joined (12/12)!",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}                                  Bed Wars",
            f"{CHAT}",
            f"{CHAT}     Protect your bed and destroy the enemy beds.",
            f"{CHAT}      Upgrade yourself and your team by collecting",
            f"{CHAT}    Iron, Gold, Emerald and Diamond from generators",
            f"{CHAT}                  to access powerful upgrades.",
            f"{CHAT}",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}Someone1 was killed by Player1. FINAL KILL!",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}                                  Bed Wars",
            f"{CHAT}",
            f"{CHAT}                          Pink - [MVP+] Me",
            f"{CHAT}",
            f"{CHAT}                   1st Killer - [MVP+] Me - 7",
            f"{CHAT}               2nd Killer - [MVP+] Player2 - 3",
            f"{CHAT}                 3rd Killer - [MVP+] Someone3 - 3",
            f"{CHAT}",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}+37 coins! (Win)",
            f"{CHAT}+50 Bed Wars Experience (Position Bonus)",
            # We join late and the overlay does not think we are in a queue when
            # we do /who. wants_shown is set to True here, so it is important that we
            # reset it to None when the game starts.
            f"{CHAT}ONLINE: Player1, Player2, Me, Player4, Player5, Player6, Player7, Player8, Player9, Player10, Player11, Player12",  # noqa: E501
            f"{CHAT}The game starts in 1 seconds!",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}                                  Bed Wars",
            f"{CHAT}",
            f"{CHAT}     Protect your bed and destroy the enemy beds.",
            f"{CHAT}      Upgrade yourself and your team by collecting",
            f"{CHAT}    Iron, Gold, Emerald and Diamond from generators",
            f"{CHAT}                  to access powerful upgrades.",
            f"{CHAT}",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
        ),
        MockedController(
            update_presence_event_set=True,
            state=create_state(
                own_username="Me",
                party_members={"Me", "Player1", "Player2"},
                lobby_players={
                    "Me",
                    "Player1",
                    "Player2",
                    "Player4",
                    "Player5",
                    "Player6",
                    "Player7",
                    "Player8",
                    "Player9",
                    "Player10",
                    "Player11",
                    "Player12",
                },
                last_game_start=0,
                in_queue=False,
                out_of_sync=True,
            ),
        ),
    ),
    (
        MockedController(state=create_state(own_username=None)),
        (
            f"{INFO}Setting user: MYIGN",
            f"{CHAT}ONLINE: Player1, Player2, MYIGN, Player4",
            f"{CHAT}Player4 has joined (4/12)!",
        ),
        MockedController(
            state=create_state(
                own_username="MYIGN",
                lobby_players={
                    "MYIGN",
                    "Player1",
                    "Player2",
                    "Player4",
                },
                out_of_sync=False,
                in_queue=True,
            )
        ),
    ),
    (
        MockedController(state=create_state(own_username=None)),
        (
            f"{INFO}Setting user: Me",
            f"{CHAT}ONLINE: Player1, Player2, Me, Player4",
            f"{CHAT}UnknownPlayer has joined (4/12)!",
        ),
        MockedController(
            state=create_state(
                own_username="Me",
                lobby_players={"UnknownPlayer"},
                out_of_sync=True,
                in_queue=True,
            )
        ),
    ),
    (
        MockedController(wants_shown=True),
        (
            f"{INFO}Setting user: Me",
            f"{CHAT}Party Moderators: Player1 ● [MVP+] Player2 ● ",
            f"{CHAT}Player1 has joined (1/12)!",
            f"{CHAT}Player2 has joined (2/12)!",
            f"{CHAT}Me has joined (3/12)!",
            f"{CHAT}Someone0 has joined (4/12)!",
            f"{CHAT}Someone1 has joined (5/12)!",
            f"{CHAT}Someone2 has joined (6/12)!",
            f"{CHAT}Someone3 has joined (7/12)!",
            f"{CHAT}Someone4 has joined (8/12)!",
            f"{CHAT}§7Someone1§7: any1 wanna party?",
            f"{CHAT}Someone5 has joined (9/12)!",
            f"{CHAT}Someone6 has joined (10/12)!",
            f"{CHAT}Someone7 has joined (11/12)!",
            f"{CHAT}Someone8 has joined (12/12)!",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}                                  Bed Wars",
            f"{CHAT}",
            f"{CHAT}     Protect your bed and destroy the enemy beds.",
            f"{CHAT}      Upgrade yourself and your team by collecting",
            f"{CHAT}    Iron, Gold, Emerald and Diamond from generators",
            f"{CHAT}                  to access powerful upgrades.",
            f"{CHAT}",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}Someone0 was killed by Player1. FINAL KILL!",
            f"{CHAT}Someone1 disconnected.",
            f"{CHAT}Someone2 disconnected.",
            f"{CHAT}Someone3 disconnected.",
            f"{CHAT}Someone4 disconnected.",
            f"{CHAT}Someone5 disconnected.",
            f"{CHAT}Someone6 disconnected.",
            f"{CHAT}Someone7 disconnected.",
            f"{CHAT}Someone1 reconnected.",
            f"{CHAT}Someone2 reconnected.",
            f"{CHAT}Someone3 reconnected.",
            f"{CHAT}Someone8 disconnected.",
            f"{CHAT}Player1 disconnected.",
            f"{CHAT}Player2 disconnected.",
        ),
        MockedController(
            state=create_state(
                own_username="Me",
                party_members={"Player1", "Player2", "Me"},
                lobby_players={
                    "Someone0",
                    "Someone1",
                    "Someone2",
                    "Someone3",
                    "Someone4",
                    "Someone5",
                    "Someone6",
                    "Someone7",
                    "Someone8",
                    "Me",
                    "Player1",
                    "Player2",
                },
                alive_players={"Someone1", "Someone2", "Someone3", "Me"},
                last_game_start=0,
                out_of_sync=True,
                in_queue=False,
            )
        ),
    ),
    (
        # Disconnect right before game starts, then rejoin
        MockedController(state=create_state(in_queue=True)),
        (
            f"{CHAT}ONLINE: Player1, Player2, Player3, Player4, Player5, Player6, Player7, OwnUsername",  # noqa: E501
            f"{CHAT}The game starts in 5 seconds!",
            f"{CHAT}The game starts in 4 seconds!",
            f"{CHAT}The game starts in 3 seconds!",
            f"{CHAT}The game starts in 2 seconds!",
            f"{CHAT}The game starts in 1 second!",
            f"{CHAT}                                     ",
            f"{CHAT}                         ",
            f"{CHAT}Sending you to mini10AR!",
        ),
        MockedController(),  # TODO: Keep the lobby?
    ),
    (
        # Disconnect during the game, then rejoin
        MockedController(state=create_state(in_queue=True)),
        (
            f"{CHAT}ONLINE: Player1, Player2, Player3, Player4, Player5, Player6, Player7, OwnUsername",  # noqa: E501
            f"{CHAT}The game starts in 5 seconds!",
            f"{CHAT}The game starts in 4 seconds!",
            f"{CHAT}The game starts in 3 seconds!",
            f"{CHAT}The game starts in 2 seconds!",
            f"{CHAT}The game starts in 1 second!",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}                                  Bed Wars",
            f"{CHAT}",
            f"{CHAT}     Protect your bed and destroy the enemy beds.",
            f"{CHAT}      Upgrade yourself and your team by collecting",
            f"{CHAT}    Iron, Gold, Emerald and Diamond from generators",
            f"{CHAT}                  to access powerful upgrades.",
            f"{CHAT}",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}                                     ",
            f"{CHAT}                         ",
            f"{CHAT}Sending you to mini10AR!",
        ),
        MockedController(),  # TODO: Keep the lobby?
    ),
    (
        MockedController(
            state=create_state(
                lobby_players={"OwnUsername", "Player1", "Player2"},
                alive_players={"OwnUsername", "Player2"},
                in_queue=False,
            ),
            wants_shown=True,
        ),
        (
            f"{CHAT}ONLINE: OwnUsername, Player2",
            f"{CHAT}Player2 was killed by OwnUsername. FINAL KILL!",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}                                  Bed Wars",
            f"{CHAT}",
            f"{CHAT}                          Pink - [MVP+] Me",
            f"{CHAT}",
            f"{CHAT}                   1st Killer - [MVP+] Me - 7",
            f"{CHAT}               2nd Killer - [MVP+] Player2 - 3",
            f"{CHAT}                 3rd Killer - [MVP+] Someone3 - 3",
            f"{CHAT}",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}OwnUsername has joined (1/12)!",
        ),
        MockedController(
            state=create_state(lobby_players={"OwnUsername"}, in_queue=True),
            update_presence_event_set=True,
            wants_shown=None,
        ),
    ),
    # Don't set in_queue in sumo
    (
        MockedController(state=create_state(in_queue=False)),
        (
            f"{CHAT}wm3EcJCi has joined (1/2)!",
            f"{CHAT}LCvmX8z has joined (2/2)!",
        ),
        MockedController(state=create_state(in_queue=False)),
    ),
    (
        MockedController(state=create_state(in_queue=False)),
        (
            f"{CHAT}wm3EcJCi has joined (1/2)!",
            f"{CHAT}LCvmX8z has joined (2/2)!",
            f"{CHAT}The game starts in 5 seconds!",
            f"{CHAT}The game starts in 4 seconds!",
            f"{CHAT}The game starts in 3 seconds!",
            f"{CHAT}The game starts in 2 seconds!",
            f"{CHAT}The game starts in 1 second!",
            f"{CHAT}Your party was split for balancing purposes.",
        ),
        MockedController(state=create_state(in_queue=False)),
    ),
    (
        MockedController(state=create_state(in_queue=False)),
        (
            f"{CHAT}wm3EcJCi has joined (1/2)!",
            f"{CHAT}LCvmX8z has joined (2/2)!",
            f"{CHAT}The game starts in 5 seconds!",
            f"{CHAT}The game starts in 4 seconds!",
            f"{CHAT}The game starts in 3 seconds!",
            f"{CHAT}The game starts in 2 seconds!",
            f"{CHAT}The game starts in 1 second!",
            f"{CHAT}Your party was split for balancing purposes.",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
            f"{CHAT}                                 Sumo Duel",
            f"{CHAT}",
            f"{CHAT}                     Eliminate your opponents!",
            f"{CHAT}",
            f"{CHAT}                         Opponent: [MVP+] iCiara",
            f"{CHAT}",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
            f"{CHAT}No stats will be affected in this round!",
            f"{CHAT}iCiara was killed by Skydeaf.",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
            f"{CHAT}                           Sumo Duel - 00:06",
            f"{CHAT}",
            f"{CHAT}                 [VIP] Skydeaf WINNER!  [MVP+] iCiara",
            f"{CHAT}",
            f"{CHAT}                     50% - Melee Accuracy - 40%",
            f"{CHAT}",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
            f"{CHAT}[GAME] [VIP] Skydeaf: gg",
            f"{CHAT}§7[SPECTATOR] §4§6✫ §4§lSumo Legend§r §b[MVP§f+§b] iCiara§f: gg",
            f"{CHAT}+10 Karma!",
            f"{CHAT}Your stats did not change because you dueled someone in your party!",  # noqa: E501
            f"{CHAT}Sending you to mini37CP!",
        ),
        MockedController(state=create_state(in_queue=False)),
    ),
)


@pytest.mark.parametrize(
    "initial_controller, loglines, target_controller", FAST_FORWARD_STATE_CASES
)
def test_fast_forward_state(
    initial_controller: MockedController,
    loglines: Iterable[str],
    target_controller: MockedController,
) -> None:
    fast_forward_state(initial_controller, loglines)

    new_controller = initial_controller
    assert new_controller == target_controller
    assert new_controller.extra == target_controller.extra


@pytest.mark.parametrize(
    "loglines, resulting_controller",
    (
        (
            (f"{CHAT}You have 1 unclaimed leveling reward!",),
            MockedController(redraw_event_set=False),
        ),
        (
            (f"{CHAT}Player1 has joined (1/16)!",),
            MockedController(
                state=create_state(lobby_players={"Player1"}, in_queue=True),
                redraw_event_set=True,
            ),
        ),
    ),
)
def test_process_loglines(
    loglines: tuple[str], resulting_controller: MockedController
) -> None:
    controller = MockedController()

    process_loglines(loglines, controller)
    assert controller == resulting_controller
    assert controller.extra == resulting_controller.extra
