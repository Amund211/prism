import unittest.mock
from collections.abc import Iterable

import pytest

from examples.overlay.behaviour import fast_forward_state
from examples.overlay.controller import OverlayController
from examples.overlay.events import (
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
    process_event,
)
from tests.examples.overlay.utils import OWN_USERNAME, MockedController, create_state

process_event_test_cases_base: tuple[
    tuple[str, OverlayController, Event, OverlayController, bool], ...
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
        MockedController(),
        InitializeAsEvent("NewPlayer"),
        MockedController(state=create_state(own_username="NewPlayer")),
        True,
    ),
    (
        "swap lobby",
        MockedController(
            state=create_state(
                party_members={"Player1", "Player2"}, lobby_players={"RandomPlayer"}
            )
        ),
        LobbySwapEvent(),
        MockedController(state=create_state(party_members={"Player1", "Player2"})),
        True,
    ),
    (
        "lobby join solo",
        MockedController(),
        LobbyJoinEvent("Player1", player_count=1, player_cap=8),
        MockedController(state=create_state(lobby_players={"Player1"}, in_queue=True)),
        True,
    ),
    (
        "lobby join doubles/fours",
        MockedController(),
        LobbyJoinEvent("Player1", player_count=1, player_cap=16),
        MockedController(state=create_state(lobby_players={"Player1"}, in_queue=True)),
        True,
    ),
    (
        "lobby leave",
        MockedController(state=create_state(lobby_players={"Leaving"})),
        LobbyLeaveEvent("Leaving"),
        MockedController(),
        True,
    ),
    (
        # The lobby is cleared and set to the received usernames
        # Your own username should always appear in the list
        "lobby list",
        MockedController(
            state=create_state(lobby_players={"PersonFromLastLobby"})
        ),  # Old members cleared
        LobbyListEvent([OWN_USERNAME, "Player1", "Player2"]),
        MockedController(
            state=create_state(
                lobby_players={OWN_USERNAME, "Player1", "Player2"}, in_queue=True
            )
        ),
        True,
    ),
    (
        "party attach",
        MockedController(),
        PartyAttachEvent("Player2"),
        MockedController(state=create_state(party_members={"Player2"})),
        True,
    ),
    (
        "party detach",
        MockedController(state=create_state(party_members={"Player1", "Player2"})),
        PartyDetachEvent(),
        MockedController(),
        True,
    ),
    (
        "party join multiple",
        MockedController(state=create_state(party_members={"Player1", "Player2"})),
        PartyJoinEvent(["Player3", "Player4"]),
        MockedController(
            state=create_state(
                party_members={"Player1", "Player2", "Player3", "Player4"}
            )
        ),
        True,
    ),
    (
        "party leave",
        MockedController(
            state=create_state(party_members={"Player1", "Player2", "Player3"})
        ),
        PartyLeaveEvent(["Player3"]),
        MockedController(state=create_state(party_members={"Player1", "Player2"})),
        True,
    ),
    (
        "party leave multiple",
        MockedController(
            state=create_state(party_members={"Player1", "Player2", "Player3"})
        ),
        PartyLeaveEvent(["Player3", "Player2"]),
        MockedController(state=create_state(party_members={"Player1"})),
        True,
    ),
    (
        "party list incoming",
        MockedController(
            state=create_state(party_members={"Player1", "Player2", "Player3"})
        ),
        PartyListIncomingEvent(),
        MockedController(),
        False,
    ),
    (
        "party list moderators",
        MockedController(state=create_state(party_members={"Player3"})),
        PartyMembershipListEvent(usernames=["Player1", "Player2"], role="moderators"),
        MockedController(
            state=create_state(party_members={"Player1", "Player2", "Player3"})
        ),
        True,
    ),
    (
        "start bedwars game",
        MockedController(state=create_state(in_queue=True)),
        StartBedwarsGameEvent(),
        MockedController(state=create_state(in_queue=False)),
        False,  # No need to redraw the screen - only hide the overlay
    ),
    (
        "end bedwars game",
        MockedController(
            state=create_state(lobby_players={"a", "bunch", "of", "players"})
        ),
        EndBedwarsGameEvent(),
        MockedController(),
        True,
    ),
    # Special cases
    (
        # New nickname when own username is unknown
        "new nickname unknown username",
        MockedController(state=create_state(own_username=None)),
        NewNicknameEvent("AmazingNick"),
        MockedController(state=create_state(own_username=None)),
        True,
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
            state=create_state(lobby_players={"Player1", "Player2"}, own_username=None)
        ),
        LobbySwapEvent(),
        MockedController(state=create_state(own_username=None)),
        True,
    ),
    (
        # Player not in party leaves party
        "player not in party leaves party",
        MockedController(state=create_state(party_members={"Player1", "Player2"})),
        PartyLeaveEvent(["RandomPlayer"]),
        MockedController(state=create_state(party_members={"Player1", "Player2"})),
        # TODO: False,
        True,
    ),
    (
        # Player not in lobby leaves lobby
        "player not in lobby leaves lobby",
        MockedController(state=create_state(lobby_players={"Player1", "Player2"})),
        LobbyLeaveEvent("RandomPlayer"),
        MockedController(state=create_state(lobby_players={"Player1", "Player2"})),
        # TODO: False,
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
        "new queue with old lobby",
        MockedController(
            state=create_state(lobby_players={"PlayerA", "PlayerB"}, in_queue=False)
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
        MockedController(state=create_state(own_username="myusername")),
        PartyLeaveEvent(["myusername"]),
        MockedController(state=create_state(own_username="myusername")),
        True,
    ),
    (
        "clear the party when you leave",
        MockedController(
            state=create_state(party_members={"abc", "def"}, own_username="myusername")
        ),
        PartyLeaveEvent(["myusername"]),
        MockedController(state=create_state(own_username="myusername")),
        True,
    ),
    (
        "party leave with no own_username",
        MockedController(state=create_state(own_username=None)),
        PartyLeaveEvent(["myusername"]),
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
    initial_controller: OverlayController,
    event: Event,
    target_controller: OverlayController,
    redraw: bool,
) -> None:
    """Assert that process_event functions properly"""
    will_redraw = process_event(initial_controller, event)

    new_controller = initial_controller
    assert new_controller == target_controller
    assert will_redraw == redraw


@pytest.mark.parametrize(
    "event",
    (
        NewNicknameEvent("AmazingNick"),
        WhisperCommandSetNickEvent(nick="AmazingNick", username="MyIGN"),
    ),
)
def test_process_event_set_nickname(event: Event) -> None:
    """Assert that set_nickname is called properly is received"""
    username = "MyIGN"
    nick = "AmazingNick"
    uuid = "MyUUID"

    controller = MockedController(
        state=create_state(own_username=username), get_uuid=lambda username: uuid
    )

    process_event(controller, event)

    # Known nicks updated
    assert controller.settings.known_nicks.get(nick, None) == {
        "uuid": uuid,
        "comment": username,
    }
    assert controller.nick_database.get(nick) == uuid

    # Settings stored
    assert controller._stored_settings == controller.settings


def test_process_event_set_api_key() -> None:
    """Assert that set_api_key is called when NewAPIKeyEvent is received"""
    controller = MockedController(hypixel_api_key="invalid-key", api_key_invalid=True)
    controller.player_cache.clear_cache = unittest.mock.MagicMock()  # type: ignore

    process_event(controller, NewAPIKeyEvent("my-new-key"))

    # Key and key invalid updated
    assert controller.hypixel_api_key == "my-new-key"
    assert not controller.api_key_invalid

    # Settings stored
    assert controller._stored_settings == controller.settings

    # Player cache cleared
    controller.player_cache.clear_cache.assert_called()


CHAT = "[Info: 2021-11-29 22:17:40.417869567: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] "  # noqa: E501
INFO = "[Info: 2021-11-29 23:26:26.372869411: GameCallbacks.cpp(162)] Game/net.minecraft.client.Minecraft (Client thread) Info "  # noqa: E501


@pytest.mark.parametrize(
    "initial_controller, loglines, target_controller",
    (
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
    ),
)
def test_fast_forward_state(
    initial_controller: OverlayController,
    loglines: Iterable[str],
    target_controller: OverlayController,
) -> None:
    fast_forward_state(initial_controller, loglines)

    new_controller = initial_controller
    assert new_controller == target_controller
