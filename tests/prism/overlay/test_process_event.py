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
from prism.overlay.real_controller import RealOverlayController
from tests.prism.overlay.utils import (
    OWN_USERNAME,
    assert_controllers_equal,
    create_controller,
    create_state,
    make_settings,
)

process_event_test_cases_base: tuple[
    tuple[str, RealOverlayController, Event, RealOverlayController, bool], ...
] = (
    (
        "initialize",
        create_controller(state=create_state(own_username=None)),
        InitializeAsEvent("NewPlayer"),
        create_controller(state=create_state(own_username="NewPlayer")),
        True,
    ),
    (
        "re-initialize",
        create_controller(
            state=create_state(
                party_members={"OwnUsername", "Player1"},
                lobby_players={"OwnUsername", "Player1"},
                alive_players={"Player1"},
                out_of_sync=True,
                in_queue=True,
            )
        ),
        InitializeAsEvent("NewPlayer"),
        create_controller(state=create_state(own_username="NewPlayer")),
        True,
    ),
    (
        "swap lobby",
        create_controller(
            wants_shown=True,
            state=create_state(
                party_members={"OwnUsername", "Player2"}, lobby_players={"RandomPlayer"}
            ),
        ),
        LobbySwapEvent(),
        create_controller(
            wants_shown=None,
            state=create_state(party_members={"OwnUsername", "Player2"}),
        ),
        True,
    ),
    (
        "swap lobby clears autowho",
        create_controller(autowho_event_set=True),
        LobbySwapEvent(),
        create_controller(autowho_event_set=False),
        True,  # TODO: Could be False
    ),
    (
        "lobby join solo",
        create_controller(wants_shown=True),
        LobbyJoinEvent("JooSGwsk", player_count=1, player_cap=8),
        create_controller(
            state=create_state(in_queue=True, lobby_players={OWN_USERNAME})
        ),
        True,
    ),
    (
        "lobby join doubles/fours",
        create_controller(wants_shown=False),
        LobbyJoinEvent("VNkQSmXugzD", player_count=1, player_cap=16),
        create_controller(
            state=create_state(in_queue=True, lobby_players={OWN_USERNAME})
        ),
        True,
    ),
    (
        "lobby leave",
        create_controller(state=create_state(lobby_players={"Player1"}, in_queue=True)),
        LobbyLeaveEvent("finTmD6Lq"),
        create_controller(state=create_state(lobby_players={"Player1"}, in_queue=True)),
        False,
    ),
    (
        "lobby leave out of queue",
        create_controller(
            wants_shown=True, state=create_state(lobby_players={"Player1"})
        ),
        LobbyLeaveEvent("idJfqPlA5T"),
        # TODO: Should the existing player get removed?
        create_controller(
            state=create_state(lobby_players={"Player1", OWN_USERNAME}, in_queue=True)
        ),
        True,
    ),
    (
        "chat message in queue",
        create_controller(state=create_state(in_queue=True)),
        ChatMessageEvent(username="Player1", message="Hello!"),
        create_controller(state=create_state(in_queue=True, lobby_players={"Player1"})),
        True,
    ),
    (
        "chat message out of queue",
        create_controller(state=create_state(in_queue=False)),
        ChatMessageEvent(username="Player1", message="Hello!"),
        create_controller(state=create_state(in_queue=False)),
        False,
    ),
    (
        "lobby list out of queue",
        create_controller(
            state=create_state(lobby_players={"PersonFromLastLobby"}, in_queue=False)
        ),
        LobbyListEvent([OWN_USERNAME, "Player1", "Player2"]),
        create_controller(
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
        create_controller(
            state=create_state(lobby_players={"PersonFromLastLobby"}, in_queue=True),
            wants_shown=False,
        ),  # Old members cleared
        LobbyListEvent([OWN_USERNAME, "Player1", "Player2"]),
        create_controller(
            state=create_state(
                lobby_players={OWN_USERNAME, "Player1", "Player2"}, in_queue=True
            ),
            wants_shown=True,
        ),
        True,
    ),
    (
        "lobby list early in game",
        create_controller(
            state=create_state(
                lobby_players={"PersonFromLastLobby"}, last_game_start=10
            ),
            wants_shown=None,
        ),  # Old members cleared
        LobbyListEvent([OWN_USERNAME, "Player1", "Player2"]),
        create_controller(
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
        create_controller(
            state=create_state(
                lobby_players={"PersonFromLastLobby"},
                last_game_start=10,
                now_func=lambda: 30,
            ),
            wants_shown=None,
        ),  # Old members cleared
        LobbyListEvent([OWN_USERNAME, "Player1", "Player2"]),
        create_controller(
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
        create_controller(),
        PartyAttachEvent("Player2"),
        create_controller(state=create_state(party_members={"OwnUsername", "Player2"})),
        True,
    ),
    (
        "party detach",
        create_controller(state=create_state(party_members={"OwnUsername", "Player2"})),
        PartyDetachEvent(),
        create_controller(),
        True,
    ),
    (
        "party join multiple",
        create_controller(state=create_state(party_members={"OwnUsername", "Player2"})),
        PartyJoinEvent(["Player3", "Player4"]),
        create_controller(
            state=create_state(
                party_members={"OwnUsername", "Player2", "Player3", "Player4"}
            )
        ),
        True,
    ),
    (
        "party leave",
        create_controller(
            state=create_state(party_members={"OwnUsername", "Player2", "Player3"})
        ),
        PartyLeaveEvent(["Player3"]),
        create_controller(state=create_state(party_members={"OwnUsername", "Player2"})),
        True,
    ),
    (
        "party leave multiple",
        create_controller(
            state=create_state(party_members={"OwnUsername", "Player2", "Player3"})
        ),
        PartyLeaveEvent(["Player3", "Player2"]),
        create_controller(state=create_state(party_members={"OwnUsername"})),
        True,
    ),
    (
        "party list incoming",
        create_controller(
            state=create_state(party_members={"OwnUsername", "Player2", "Player3"})
        ),
        PartyListIncomingEvent(),
        create_controller(),
        False,
    ),
    (
        "party list moderators",
        create_controller(state=create_state(party_members={"OwnUsername"})),
        PartyMembershipListEvent(usernames=["Player1", "Player2"], role="moderators"),
        create_controller(
            state=create_state(party_members={"Player1", "Player2", "OwnUsername"})
        ),
        True,
    ),
    (
        "bedwars game starting soon",
        create_controller(),
        BedwarsGameStartingSoonEvent(seconds=5),
        create_controller(),
        False,  # No need to redraw the screen - only show the overlay
    ),
    (
        "bedwars game starting soon, already in queue",
        create_controller(state=create_state(in_queue=True)),
        BedwarsGameStartingSoonEvent(seconds=4),
        create_controller(state=create_state(in_queue=True)),
        False,  # No need to redraw the screen - only show the overlay
    ),
    (
        "start bedwars game",
        create_controller(
            wants_shown=False, state=create_state(in_queue=True, now_func=lambda: 1234)
        ),
        StartBedwarsGameEvent(is_bedwars_duel=False),
        create_controller(
            wants_shown=None,
            autowho_event_set=True,
            state=create_state(in_queue=False, out_of_sync=True, last_game_start=1234),
        ),
        False,  # No need to redraw the screen - only hide the overlay
    ),
    (
        "start bedwars duels game when disabled in duels",
        create_controller(
            wants_shown=False,
            state=create_state(in_queue=True),
            # Disabled in duels is the default
        ),
        StartBedwarsGameEvent(is_bedwars_duel=True),
        create_controller(
            wants_shown=False,
            state=create_state(in_queue=True),
        ),
        False,
    ),
    (
        "start bedwars duels game when enabled in duels",
        create_controller(
            wants_shown=False,
            state=create_state(in_queue=True, now_func=lambda: 1234),
            settings=make_settings(activate_in_bedwars_duels=True),
        ),
        StartBedwarsGameEvent(is_bedwars_duel=True),
        create_controller(
            wants_shown=None,
            autowho_event_set=True,
            state=create_state(in_queue=False, out_of_sync=True, last_game_start=1234),
            settings=make_settings(activate_in_bedwars_duels=True),
        ),
        False,  # No need to redraw the screen - only hide the overlay
    ),
    (
        "start bedwars game when not ready",
        # Got a start bedwars game event while fast forwarding -> don't autowho
        create_controller(
            ready=False,
            wants_shown=False,
            state=create_state(in_queue=True, now_func=lambda: 1234),
        ),
        StartBedwarsGameEvent(is_bedwars_duel=False),
        create_controller(
            ready=False,
            wants_shown=None,
            state=create_state(in_queue=False, out_of_sync=True, last_game_start=1234),
        ),
        False,
    ),
    (
        "final kill",
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"},
                alive_players={"Player1", "Player2"},
            )
        ),
        BedwarsFinalKillEvent(
            dead_player="Player1",
            raw_message="Player1 was killed by Player2. FINAL KILL!",
        ),
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        True,
    ),
    (
        "final kill on already dead player",
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        BedwarsFinalKillEvent(
            dead_player="Player1",
            raw_message="Player1 was killed by Player2. FINAL KILL!",
        ),
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        True,  # TODO: Could be False
    ),
    (
        "disconnect",
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"},
                alive_players={"Player1", "Player2"},
            )
        ),
        BedwarsDisconnectEvent(username="Player1"),
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        True,
    ),
    (
        "disconnect while not alive",
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        BedwarsDisconnectEvent(username="Player1"),
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        True,  # TODO: Could be False
    ),
    (
        "disconnect while not in lobby",
        create_controller(
            state=create_state(lobby_players={"Player2"}, alive_players={"Player2"})
        ),
        BedwarsDisconnectEvent(username="Player1"),
        create_controller(
            state=create_state(
                lobby_players={"Player2", "Player1"}, alive_players={"Player2"}
            )
        ),
        True,
    ),
    (
        "disconnect while not in lobby, but alive somehow",
        create_controller(
            state=create_state(
                lobby_players={"Player2"}, alive_players={"Player1", "Player2"}
            )
        ),
        BedwarsDisconnectEvent(username="Player1"),
        create_controller(
            state=create_state(lobby_players={"Player2"}, alive_players={"Player2"})
        ),
        True,
    ),
    (
        "reconnect",
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        BedwarsReconnectEvent(username="Player1"),
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"},
                alive_players={"Player1", "Player2"},
            )
        ),
        True,
    ),
    (
        "disconnect while alive",
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        BedwarsReconnectEvent(username="Player2"),
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"}, alive_players={"Player2"}
            )
        ),
        True,  # TODO: Could be False
    ),
    (
        "reconnect while not in lobby",
        create_controller(
            state=create_state(lobby_players={"Player2"}, alive_players={"Player2"})
        ),
        BedwarsReconnectEvent(username="Player1"),
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"},
                alive_players={"Player1", "Player2"},
            )
        ),
        True,
    ),
    (
        "reconnect while not in lobby, but alive somehow",
        create_controller(
            state=create_state(
                lobby_players={"Player2"}, alive_players={"Player1", "Player2"}
            )
        ),
        BedwarsReconnectEvent(username="Player1"),
        create_controller(
            state=create_state(
                lobby_players={"Player1", "Player2"},
                alive_players={"Player1", "Player2"},
            )
        ),
        True,
    ),
    (
        "end bedwars game",
        create_controller(
            state=create_state(lobby_players={"a", "bunch", "of", "players"})
        ),
        EndBedwarsGameEvent(),
        create_controller(update_presence_event_set=True),
        True,
    ),
    (
        "bedwars game end clears autowho",
        create_controller(autowho_event_set=True),
        EndBedwarsGameEvent(),
        create_controller(autowho_event_set=False, update_presence_event_set=True),
        True,  # TODO: Could be False
    ),
    # Special cases
    (
        # New nickname when own username is unknown
        "new nickname unknown username",
        create_controller(state=create_state(own_username=None)),
        NewNicknameEvent("AmazingNick"),
        create_controller(state=create_state(own_username=None)),
        False,
    ),
    (
        # Party leave when own username is unknown
        "party leave unknown username",
        create_controller(
            state=create_state(party_members={"Player1", "Player2"}, own_username=None)
        ),
        PartyDetachEvent(),
        create_controller(state=create_state(own_username=None)),
        True,
    ),
    (
        # Lobby swap when own username is unknown
        "lobby swap unknown username",
        create_controller(
            wants_shown=False,
            state=create_state(lobby_players={"Player1", "Player2"}, own_username=None),
        ),
        LobbySwapEvent(),
        create_controller(wants_shown=None, state=create_state(own_username=None)),
        True,
    ),
    (
        # Player not in party leaves party
        "player not in party leaves party",
        create_controller(state=create_state(party_members={"OwnUsername", "Player2"})),
        PartyLeaveEvent(["RandomPlayer"]),
        create_controller(state=create_state(party_members={"OwnUsername", "Player2"})),
        # TODO: False,
        True,
    ),
    (
        # Player not in lobby leaves lobby
        "player not in lobby leaves lobby",
        create_controller(
            state=create_state(in_queue=True, lobby_players={"Player1", "Player2"})
        ),
        LobbyLeaveEvent("RandomPlayer"),
        create_controller(
            state=create_state(in_queue=True, lobby_players={"Player1", "Player2"})
        ),
        False,
    ),
    (
        "final kill on player not in lobby",
        create_controller(state=create_state(lobby_players={"Player2"})),
        BedwarsFinalKillEvent(
            dead_player="Player1",
            raw_message="Player1 was killed by Player2. FINAL KILL!",
        ),
        create_controller(
            state=create_state(
                lobby_players={"Player2", "Player1"}, alive_players={"Player2"}
            )
        ),
        True,
    ),
    (
        "final kill on player not in lobby, but alive somehow",
        create_controller(
            state=create_state(
                lobby_players={"Player2"}, alive_players={"Player1", "Player2"}
            )
        ),
        BedwarsFinalKillEvent(
            dead_player="Player1",
            raw_message="Player1 was killed by Player2. FINAL KILL!",
        ),
        create_controller(
            state=create_state(lobby_players={"Player2"}, alive_players={"Player2"})
        ),
        True,
    ),
    (
        # Small player cap -> not bedwars
        "player join non bedwars",
        create_controller(),
        LobbyJoinEvent("lll7a9UqaBV4h", player_count=2, player_cap=2),
        create_controller(),
        False,
    ),
    (
        "too few known players in lobby",
        create_controller(),
        LobbyJoinEvent("rkxyCRIUchq", player_count=5, player_cap=16),
        create_controller(
            state=create_state(in_queue=True, lobby_players={OWN_USERNAME})
        ),
        True,
    ),
    (
        "too many known players in lobby",
        create_controller(
            state=create_state(lobby_players={"PlayerA", "PlayerB"}, in_queue=True)
        ),
        LobbyJoinEvent("RoUmY6hqDeAZo", player_count=1, player_cap=16),
        create_controller(
            state=create_state(lobby_players={"PlayerA", "PlayerB"}, in_queue=True)
        ),
        False,
    ),
    (
        "too many known players in lobby, too few remaining",
        create_controller(
            state=create_state(
                lobby_players={"PlayerA", "PlayerB", "PlayerC"}, in_queue=True
            )
        ),
        LobbyJoinEvent("UgpXFdApWotX9", player_count=3, player_cap=16),
        create_controller(
            state=create_state(
                lobby_players={"PlayerA", "PlayerB", "PlayerC"}, in_queue=True
            )
        ),
        False,
    ),
    (
        "new queue with in-sync old lobby (weird)",
        create_controller(
            state=create_state(lobby_players={"PlayerA", "PlayerB"}, in_queue=False)
        ),
        LobbyJoinEvent("mY7r7eVmAP", player_count=8, player_cap=16),
        create_controller(
            state=create_state(
                lobby_players={"PlayerA", "PlayerB", OWN_USERNAME}, in_queue=True
            )
        ),
        True,
    ),
    (
        "new queue with lobby from previous game",
        create_controller(
            state=create_state(
                lobby_players={"PlayerA", "PlayerB"},
                alive_players={"PlayerB"},
                in_queue=False,
            )
        ),
        LobbyJoinEvent("oU9ivfVPB", player_count=8, player_cap=16),
        create_controller(
            state=create_state(in_queue=True, lobby_players={OWN_USERNAME})
        ),
        True,
    ),
    (
        "new queue with old lobby and too many players",
        create_controller(
            state=create_state(lobby_players={"PlayerA", "PlayerB"}, in_queue=False)
        ),
        LobbyJoinEvent("uTreXGQE", player_count=1, player_cap=16),
        create_controller(
            state=create_state(
                lobby_players={"PlayerA", "PlayerB", OWN_USERNAME}, in_queue=True
            )
        ),
        True,
    ),
    (
        "don't remove yourself from the party",
        create_controller(state=create_state()),
        PartyLeaveEvent(["OwnUsername"]),
        create_controller(state=create_state()),
        True,
    ),
    (
        "clear the party when you leave",
        create_controller(
            state=create_state(party_members={"OwnUsername", "abc", "def"})
        ),
        PartyLeaveEvent(["OwnUsername"]),
        create_controller(state=create_state()),
        True,
    ),
    (
        "party leave with no own_username",
        create_controller(state=create_state(own_username=None)),
        PartyLeaveEvent(["OwnUsername"]),
        create_controller(state=create_state(own_username=None)),
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
    initial_controller: RealOverlayController,
    event: Event,
    target_controller: RealOverlayController,
    redraw: bool,
) -> None:
    """Assert that process_event functions properly"""
    initial_controller.state, will_redraw = process_event(initial_controller, event)

    new_controller = initial_controller
    assert_controllers_equal(new_controller, target_controller)
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

    controller = create_controller(state=create_state(own_username=username))

    with unittest.mock.patch(
        "prism.overlay.process_event.set_nickname"
    ) as patched_set_nickname:
        new_state, will_redraw = process_event(controller, event)

    patched_set_nickname.assert_called_once_with(
        nick=nick, username=username, controller=controller
    )
    assert not will_redraw  # set_nickname sets redraw_flag


def test_process_event_bedwars_game_ended() -> None:
    """
    Assert that bedwars_game_ended is called when EndBedwarsGameEvent is received
    """
    controller = create_controller()

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
        create_controller(state=create_state(own_username=None)),
        (
            f"{INFO}Setting user: Me",
            f"{CHAT}Party Moderators: Player1 ● [MVP+] Player2 ● ",
            f"{CHAT}XAjvE94RD7vM has joined (1/16)!",
            f"{CHAT}MCvlmdrj has joined (2/16)!",
            f"{CHAT}hhSWoTBsCEubb4 has joined (3/16)!",
            f"{CHAT}DH0Jtkt0d has joined (4/16)!",
            f"{CHAT}[MVP+] Player1: hows ur day?",
        ),
        create_controller(
            state=create_state(
                own_username="Me",
                party_members={"Me", "Player1", "Player2"},
                lobby_players={"Me", "Player1", "Player2", "Player1"},
                in_queue=True,
            )
        ),
    ),
    (
        # Excerpt from new multiver lunar logfile
        create_controller(state=create_state(own_username=None)),
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
        create_controller(state=create_state(own_username="YourIGN")),
    ),
    (
        # Ensure game starts in lucky blocks
        create_controller(
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
            "[16:12:39] [Client thread/INFO]: [CHAT] ObqbE8fS has joined (16/16)!",  # noqa: E501
            "[16:12:40] [Client thread/INFO]: [CHAT] ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            "[16:12:40] [Client thread/INFO]: [CHAT]                        Bed Wars Lucky Blocks",  # noqa: E501
            "[16:12:40] [Client thread/INFO]: [CHAT] ",
            "[16:12:40] [Client thread/INFO]: [CHAT]     Collect Lucky Blocks from resource generators",  # noqa: E501
            "[16:12:40] [Client thread/INFO]: [CHAT]        to receive random loot! Break them to reveal",  # noqa: E501
            "[16:12:40] [Client thread/INFO]: [CHAT]                              their contents!",  # noqa: E501
            "[16:12:40] [Client thread/INFO]: [CHAT] ",
            "[16:12:40] [Client thread/INFO]: [CHAT] ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
        ),
        create_controller(
            autowho_event_set=True,
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
                },
            ),
        ),
    ),
    (
        create_controller(state=create_state(own_username=None)),
        (
            f"{INFO}Setting user: Me",
            f"{CHAT}Party Moderators: Player1 ● [MVP+] Player2 ● ",
            f"{CHAT}IL7pCI has joined (1/12)!",
            f"{CHAT}AjR1XhdMEqf06k has joined (2/12)!",
            f"{CHAT}0KFTnl has joined (3/12)!",
            f"{CHAT}WSmZb1XNM has joined (4/12)!",
            f"{CHAT}NMSP1Ml0 has joined (5/12)!",
            f"{CHAT}hGYMEkWjDb42I has joined (6/12)!",
            f"{CHAT}F3S2iUH2mbuBxH has joined (7/12)!",
            f"{CHAT}pOUkBao1Cl has joined (8/12)!",
            f"{CHAT}§7Someone1§7: any1 wanna party?",
            f"{CHAT}GZlkCqQPa3UKH8 has joined (9/12)!",
            f"{CHAT}GUidHWzaN91VGk has joined (10/12)!",
            f"{CHAT}t2jcO9qz has joined (11/12)!",
            f"{CHAT}ygIvIo has joined (12/12)!",
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
            f"{CHAT}ONLINE: Player100, Player200, Me, Player400, Player500, Player600, Player700, Player800, Player900, Player1000, Player1100, Player1200",  # noqa: E501
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}                                  Bed Wars",
            f"{CHAT}",
            f"{CHAT}                          Pink - [MVP+] Me",
            f"{CHAT}",
            f"{CHAT}                   1st Killer - [MVP+] Me - 7",
            f"{CHAT}               2nd Killer - [MVP+] Player200 - 3",
            f"{CHAT}                 3rd Killer - [MVP+] Someone1 - 3",
            f"{CHAT}",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}+37 coins! (Win)",
            f"{CHAT}+50 Bed Wars Experience (Position Bonus)",
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
            f"{CHAT}ONLINE: Player1, Player2, Me, Player4, Player5, Player6, Player7, Player8, Player9, Player10, Player11, Player12",  # noqa: E501
        ),
        create_controller(
            update_presence_event_set=True,
            autowho_event_set=True,
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
            ),
        ),
    ),
    (
        create_controller(state=create_state(own_username=None)),
        (
            f"{INFO}Setting user: MYIGN",
            f"{CHAT}ONLINE: Player1, Player2, MYIGN, Player4",
            f"{CHAT}Of6neF has joined (4/12)!",
        ),
        create_controller(
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
        create_controller(state=create_state(own_username=None)),
        (
            f"{INFO}Setting user: Me",
            f"{CHAT}ONLINE: Player1, Player2, Me, Player4",
            f"{CHAT}EIfDv has joined (4/12)!",
        ),
        create_controller(
            state=create_state(
                own_username="Me",
                lobby_players={"Player1", "Player2", "Me", "Player4"},
                in_queue=True,
            )
        ),
    ),
    (
        create_controller(wants_shown=True),
        (
            f"{INFO}Setting user: Me",
            f"{CHAT}Party Moderators: Teammate1 ● [MVP+] Teammate2 ● ",
            f"{CHAT}gWpaeB2pjU4pu5 has joined (1/12)!",
            f"{CHAT}jzYOXLjWBDmds4 has joined (2/12)!",
            f"{CHAT}1xNyc has joined (3/12)!",
            f"{CHAT}TJYv has joined (4/12)!",
            f"{CHAT}dDlSuj has joined (5/12)!",
            f"{CHAT}GHsw8HrKf has joined (6/12)!",
            f"{CHAT}6Ty0CVMl4llLl7 has joined (7/12)!",
            f"{CHAT}4c9buS0oDKCo has joined (8/12)!",
            f"{CHAT}§7Someone1§7: any1 wanna party?",
            f"{CHAT}Eq1NdJ6 has joined (9/12)!",
            f"{CHAT}ULCU0ovR has joined (10/12)!",
            f"{CHAT}t4R67KT has joined (11/12)!",
            f"{CHAT}6m0uKCGuo0i has joined (12/12)!",
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
            f"{CHAT}Teammate2 disconnected.",
        ),
        create_controller(
            autowho_event_set=True,
            state=create_state(
                own_username="Me",
                party_members={"Teammate1", "Teammate2", "Me"},
                lobby_players={
                    "Me",
                    "Teammate1",
                    "Teammate2",
                    "Someone0",
                    "Someone1",
                    "Someone2",
                    "Someone3",
                    "Someone4",
                    "Someone5",
                    "Someone6",
                    "Someone7",
                    "Someone8",
                    "Player1",
                },
                alive_players={"Me", "Teammate1", "Someone1", "Someone2", "Someone3"},
                last_game_start=0,
                out_of_sync=True,
                in_queue=False,
            ),
        ),
    ),
    (
        # Disconnect right before game starts, then rejoin
        create_controller(state=create_state(in_queue=True)),
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
        create_controller(),  # TODO: Keep the lobby?
    ),
    (
        # Disconnect during the game, then rejoin
        create_controller(state=create_state(in_queue=True)),
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
        create_controller(),  # TODO: Keep the lobby?
    ),
    (
        create_controller(
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
            f"{CHAT}lV4Za9p has joined (1/12)!",
        ),
        create_controller(
            state=create_state(in_queue=True, lobby_players={OWN_USERNAME}),
            update_presence_event_set=True,
            wants_shown=None,
        ),
    ),
    # Don't set in_queue in sumo
    (
        create_controller(state=create_state(in_queue=False)),
        (
            f"{CHAT}wm3EcJCi has joined (1/2)!",
            f"{CHAT}LCvmX8z has joined (2/2)!",
        ),
        create_controller(state=create_state(in_queue=False)),
    ),
    (
        create_controller(state=create_state(in_queue=False)),
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
        create_controller(state=create_state(in_queue=False)),
    ),
    (
        create_controller(state=create_state(in_queue=False)),
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
        create_controller(state=create_state(in_queue=False)),
    ),
    (
        # Regular queue, start
        create_controller(state=create_state(now_func=lambda: 3.5)),
        (
            f"{CHAT}hhSWoTBsCEubb4 has joined (16/16)!",
            f"{CHAT}[MVP+] Player1: hows ur day?",
            f"{CHAT}[MVP+] Leaving: I'm going to leave",
            f"{CHAT}MCvlmdrj has quit!",
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
            f"{CHAT}[SHOUT] [RED] [VIP+] Player2: some chat message",
        ),
        create_controller(
            autowho_event_set=True,
            state=create_state(
                lobby_players={
                    OWN_USERNAME,
                    "Player1",
                    "Player2",
                    "Leaving",  # Still left in the lobby until user does /who
                },
                out_of_sync=True,
                last_game_start=3.5,
            ),
        ),
    ),
    (
        # Regular queue, start, end
        create_controller(state=create_state()),
        (
            f"{CHAT}hhSWoTBsCEubb4 has joined (16/16)!",
            f"{CHAT}[MVP+] Player1: hows ur day?",
            f"{CHAT}[MVP+] Leaving: I'm going to leave",
            f"{CHAT}MCvlmdrj has quit!",
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
            f"{CHAT}[SHOUT] [RED] [VIP+] Player2: some chat message",
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
        ),
        create_controller(
            state=create_state(),
            update_presence_event_set=True,
        ),
    ),
    (
        # Regular queue, start and /who
        create_controller(state=create_state(now_func=lambda: 1.5)),
        (
            f"{CHAT}hhSWoTBsCEubb4 has joined (16/16)!",
            f"{CHAT}[MVP+] Player2: hows ur day?",
            f"{CHAT}[MVP+] Leaving: I'm going to leave",
            f"{CHAT}MCvlmdrj has quit!",
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
            f"{CHAT}ONLINE: Player1, Player2, Player3, Player4, Player5, Player6, Player7, Player8, Player9, Player10, Player11, Player12, Player13, Player14, Player15",  # noqa: E501
            f"{CHAT}[SHOUT] [RED] [VIP+] Player2: some chat message",
        ),
        create_controller(
            autowho_event_set=True,
            state=create_state(
                lobby_players={
                    "Player1",
                    "Player2",
                    "Player3",
                    "Player4",
                    "Player5",
                    "Player6",
                    "Player7",
                    "Player8",
                    "Player9",
                    "Player10",
                    "Player11",
                    "Player12",
                    "Player13",
                    "Player14",
                    "Player15",
                },
                last_game_start=1.5,
            ),
        ),
    ),
    (
        # Setting user clears state
        create_controller(),
        (
            f"{CHAT}hhSWoTBsCEubb4 has joined (16/16)!",
            f"{CHAT}[MVP+] Player2: hows ur day?",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{CHAT}                                  Bed Wars",
            f"{CHAT}",
            f"{CHAT}     Protect your bed and destroy the enemy beds.",
            f"{CHAT}      Upgrade yourself and your team by collecting",
            f"{CHAT}    Iron, Gold, Emerald and Diamond from generators",
            f"{CHAT}                  to access powerful upgrades.",
            f"{CHAT}",
            f"{CHAT}▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",  # noqa: E501
            f"{INFO}Setting user: MyUsername",
        ),
        create_controller(
            autowho_event_set=True, state=create_state(own_username="MyUsername")
        ),
    ),
)


@pytest.mark.parametrize(
    "initial_controller, loglines, target_controller", FAST_FORWARD_STATE_CASES
)
def test_fast_forward_state(
    initial_controller: RealOverlayController,
    loglines: Iterable[str],
    target_controller: RealOverlayController,
) -> None:
    fast_forward_state(initial_controller, loglines)

    new_controller = initial_controller
    assert_controllers_equal(new_controller, target_controller)


@pytest.mark.parametrize(
    "loglines, resulting_controller",
    (
        (
            (f"{CHAT}You have 1 unclaimed leveling reward!",),
            create_controller(redraw_event_set=False),
        ),
        (
            (f"{CHAT}hhSWoTBsCEubb4 has joined (1/16)!",),
            create_controller(
                state=create_state(in_queue=True, lobby_players={OWN_USERNAME}),
                redraw_event_set=True,
            ),
        ),
        (
            (f"{CHAT}ONLINE: Player1, Player2",),
            create_controller(
                state=create_state(lobby_players={"Player1", "Player2"}),
                redraw_event_set=True,
                wants_shown=True,
            ),
        ),
    ),
)
def test_process_loglines(
    loglines: tuple[str], resulting_controller: RealOverlayController
) -> None:
    controller = create_controller()

    process_loglines(loglines, controller)
    assert_controllers_equal(controller, resulting_controller)
