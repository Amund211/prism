import unittest.mock
from typing import Callable, Iterable, Optional

import pytest

from examples.overlay.parsing import (
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
from examples.overlay.state import (
    OverlayState,
    SetNickname,
    fast_forward_state,
    update_state,
)

OWN_USERNAME = "OwnUsername"


def create_state(
    party_members: set[str] = set(),
    lobby_players: set[str] = set(),
    set_api_key: Optional[Callable[[str], None]] = None,
    set_nickname: Optional[SetNickname] = None,
    out_of_sync: bool = False,
    in_queue: bool = False,
    own_username: Optional[str] = OWN_USERNAME,
) -> OverlayState:
    yourself = set() if own_username is None else set([own_username])
    return OverlayState(
        party_members=party_members | yourself,
        lobby_players=lobby_players,
        set_api_key=set_api_key or unittest.mock.MagicMock(),
        set_nickname=set_nickname or unittest.mock.MagicMock(),
        out_of_sync=out_of_sync,
        in_queue=in_queue,
        own_username=own_username,
    )


update_state_test_cases_base = (
    (
        "initialize",
        create_state(own_username=None),
        InitializeAsEvent("NewPlayer"),
        create_state(own_username="NewPlayer"),
        True,
    ),
    (
        "re-initialize",
        create_state(),
        InitializeAsEvent("NewPlayer"),
        create_state(own_username="NewPlayer"),
        True,
    ),
    (
        # See more interesting test function for this below
        "new nickname",
        create_state(),
        NewNicknameEvent("AmazingNick"),
        create_state(),
        True,
    ),
    (
        "swap lobby",
        create_state(
            party_members={"Player1", "Player2"}, lobby_players={"RandomPlayer"}
        ),
        LobbySwapEvent(),
        create_state(party_members={"Player1", "Player2"}),
        True,
    ),
    (
        "lobby join solo",
        create_state(),
        LobbyJoinEvent("Player1", player_count=1, player_cap=8),
        create_state(lobby_players={"Player1"}, in_queue=True),
        True,
    ),
    (
        "lobby join doubles/fours",
        create_state(),
        LobbyJoinEvent("Player1", player_count=1, player_cap=16),
        create_state(lobby_players={"Player1"}, in_queue=True),
        True,
    ),
    (
        "lobby leave",
        create_state(lobby_players={"Leaving"}),
        LobbyLeaveEvent("Leaving"),
        create_state(),
        True,
    ),
    (
        # The lobby is cleared and set to the received usernames
        # Your own username should always appear in the list
        "lobby list",
        create_state(lobby_players={"PersonFromLastLobby"}),  # Old members cleared
        LobbyListEvent([OWN_USERNAME, "Player1", "Player2"]),
        create_state(lobby_players={OWN_USERNAME, "Player1", "Player2"}, in_queue=True),
        True,
    ),
    (
        "party attach",
        create_state(),
        PartyAttachEvent("Player2"),
        create_state(party_members={"Player2"}),
        True,
    ),
    (
        "party detach",
        create_state(party_members={"Player1", "Player2"}),
        PartyDetachEvent(),
        create_state(),
        True,
    ),
    (
        "party join multiple",
        create_state(party_members={"Player1", "Player2"}),
        PartyJoinEvent(["Player3", "Player4"]),
        create_state(party_members={"Player1", "Player2", "Player3", "Player4"}),
        True,
    ),
    (
        "party leave",
        create_state(party_members={"Player1", "Player2", "Player3"}),
        PartyLeaveEvent(["Player3"]),
        create_state(party_members={"Player1", "Player2"}),
        True,
    ),
    (
        "party leave multiple",
        create_state(party_members={"Player1", "Player2", "Player3"}),
        PartyLeaveEvent(["Player3", "Player2"]),
        create_state(party_members={"Player1"}),
        True,
    ),
    (
        "party list incoming",
        create_state(party_members={"Player1", "Player2", "Player3"}),
        PartyListIncomingEvent(),
        create_state(),
        False,
    ),
    (
        "party list moderators",
        create_state(party_members={"Player3"}),
        PartyMembershipListEvent(usernames=["Player1", "Player2"], role="moderators"),
        create_state(party_members={"Player1", "Player2", "Player3"}),
        True,
    ),
    (
        "start bedwars game",
        create_state(in_queue=True),
        StartBedwarsGameEvent(),
        create_state(in_queue=False),
        False,  # No need to redraw the screen - only hide the overlay
    ),
    (
        "end bedwars game",
        create_state(lobby_players={"a", "bunch", "of", "players"}),
        EndBedwarsGameEvent(),
        create_state(),
        True,
    ),
    (
        "whisper command set nick",
        create_state(),
        WhisperCommandSetNickEvent(nick="alkj", username="LKJLKJ"),
        create_state(),
        True,
    ),
    # Special cases
    (
        # New nickname when own username is unknown
        "new nickname unknown username",
        create_state(own_username=None),
        NewNicknameEvent("AmazingNick"),
        create_state(own_username=None),
        True,
    ),
    (
        # Party leave when own username is unknown
        "party leave unknown username",
        create_state(party_members={"Player1", "Player2"}, own_username=None),
        PartyDetachEvent(),
        create_state(own_username=None),
        True,
    ),
    (
        # Lobby swap when own username is unknown
        "lobby swap unknown username",
        create_state(lobby_players={"Player1", "Player2"}, own_username=None),
        LobbySwapEvent(),
        create_state(own_username=None),
        True,
    ),
    (
        # Player not in party leaves party
        "player not in party leaves party",
        create_state(party_members={"Player1", "Player2"}),
        PartyLeaveEvent(["RandomPlayer"]),
        create_state(party_members={"Player1", "Player2"}),
        # TODO: False,
        True,
    ),
    (
        # Player not in lobby leaves lobby
        "player not in lobby leaves lobby",
        create_state(lobby_players={"Player1", "Player2"}),
        LobbyLeaveEvent("RandomPlayer"),
        create_state(lobby_players={"Player1", "Player2"}),
        # TODO: False,
        True,
    ),
    (
        # Small player cap -> not bedwars
        "player join non bedwars",
        create_state(),
        LobbyJoinEvent("Player1", player_count=2, player_cap=2),
        create_state(),
        False,
    ),
    (
        # Player count too low -> out of sync
        "too few known players in lobby",
        create_state(),
        LobbyJoinEvent("Player1", player_count=5, player_cap=16),
        create_state(lobby_players={"Player1"}, out_of_sync=True, in_queue=True),
        True,
    ),
    (
        # Player count too high -> clear lobby
        "too many known players in lobby",
        create_state(lobby_players={"PlayerA", "PlayerB"}, in_queue=True),
        LobbyJoinEvent("Player1", player_count=1, player_cap=16),
        create_state(lobby_players={"Player1"}, in_queue=True),
        True,
    ),
    (
        # Player count too high -> clear lobby, still out of sync
        "too many known players in lobby, too few remaining",
        create_state(lobby_players={"PlayerA", "PlayerB", "PlayerC"}, in_queue=True),
        LobbyJoinEvent("Player1", player_count=3, player_cap=16),
        create_state(lobby_players={"Player1"}, out_of_sync=True, in_queue=True),
        True,
    ),
    (
        "new queue with old lobby",
        create_state(lobby_players={"PlayerA", "PlayerB"}, in_queue=False),
        LobbyJoinEvent("Player1", player_count=8, player_cap=16),
        create_state(lobby_players={"Player1"}, out_of_sync=True, in_queue=True),
        True,
    ),
    (
        "new queue with old lobby and too many players",
        create_state(lobby_players={"PlayerA", "PlayerB"}, in_queue=False),
        LobbyJoinEvent("Player1", player_count=1, player_cap=16),
        create_state(lobby_players={"Player1"}, in_queue=True),
        True,
    ),
    (
        "don't remove yourself from the party",
        create_state(own_username="myusername"),
        PartyLeaveEvent(["myusername"]),
        create_state(own_username="myusername"),
        True,
    ),
    (
        "clear the party when you leave",
        create_state(party_members={"abc", "def"}, own_username="myusername"),
        PartyLeaveEvent(["myusername"]),
        create_state(own_username="myusername"),
        True,
    ),
    (
        "party leave with no own_username",
        create_state(own_username=None),
        PartyLeaveEvent(["myusername"]),
        create_state(own_username=None),
        True,
    ),
)

update_state_test_ids = [test_case[0] for test_case in update_state_test_cases_base]
assert len(update_state_test_ids) == len(
    set(update_state_test_ids)
), "Test ids should be unique"

update_state_test_cases = [test_case[1:] for test_case in update_state_test_cases_base]


@pytest.mark.parametrize(
    "initial_state, event, target_state, redraw",
    update_state_test_cases,
    ids=update_state_test_ids,
)
def test_update_state(
    initial_state: OverlayState, event: Event, target_state: OverlayState, redraw: bool
) -> None:
    """Assert that update_state functions properly"""
    will_redraw = update_state(initial_state, event)

    new_state = initial_state
    assert new_state == target_state
    assert will_redraw == redraw


def test_update_state_set_nickname() -> None:
    """Assert that set_nickname is called when NewNicknameEvent is received"""
    state = create_state(own_username="Me")
    update_state(state, NewNicknameEvent("AmazingNick"))
    state.set_nickname.assert_called_with(  # type: ignore
        username="Me", nick="AmazingNick"
    )


def test_update_state_set_api_key() -> None:
    """Assert that set_api_key is called when NewAPIKeyEvent is received"""
    state = create_state()
    update_state(state, NewAPIKeyEvent("my-new-key"))
    state.set_api_key.assert_called_with("my-new-key")  # type: ignore


CHAT = "[Info: 2021-11-29 22:17:40.417869567: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] "  # noqa: E501
INFO = "[Info: 2021-11-29 23:26:26.372869411: GameCallbacks.cpp(162)] Game/net.minecraft.client.Minecraft (Client thread) Info "  # noqa: E501


@pytest.mark.parametrize(
    "initial_state, loglines, target_state",
    (
        (
            create_state(own_username=None),
            (
                f"{INFO}Setting user: Me",
                f"{CHAT}Party Moderators: Player1 ● [MVP+] Player2 ● ",
                f"{CHAT}Player1 has joined (1/16)!",
                f"{CHAT}Player2 has joined (2/16)!",
                f"{CHAT}Me has joined (3/16)!",
                f"{CHAT}Someone has joined (4/16)!",
                f"{CHAT}[MVP+] Player1: hows ur day?",
            ),
            create_state(
                own_username="Me",
                party_members={"Me", "Player1", "Player2"},
                lobby_players={"Me", "Player1", "Player2", "Someone"},
                in_queue=True,
            ),
        ),
    ),
)
def test_fast_forward_state(
    initial_state: OverlayState, loglines: Iterable[str], target_state: OverlayState
) -> None:
    fast_forward_state(initial_state, loglines)

    new_state = initial_state
    assert new_state == target_state
