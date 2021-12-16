from typing import Optional

import pytest

from examples.sidelay.parsing import (
    Event,
    InitializeAsEvent,
    LobbyJoinEvent,
    LobbyLeaveEvent,
    LobbyListEvent,
    LobbySwapEvent,
    PartyAttachEvent,
    PartyDetachEvent,
    PartyJoinEvent,
    PartyLeaveEvent,
    PartyListIncomingEvent,
    PartyMembershipListEvent,
)
from examples.sidelay.state import OverlayState, update_state

OWN_USERNAME = "OwnUsername"


def create_state(
    party_members: set[str] = set(),
    lobby_players: set[str] = set(),
    out_of_sync: bool = False,
    own_username: Optional[str] = OWN_USERNAME,
) -> OverlayState:
    yourself = set() if own_username is None else set([own_username])
    return OverlayState(
        party_members=party_members | yourself,
        lobby_players=lobby_players | yourself,
        out_of_sync=out_of_sync,
        own_username=own_username,
    )


@pytest.mark.parametrize(
    "initial_state, event, target_state, redraw",
    (
        (
            create_state(own_username=None),
            InitializeAsEvent("NewPlayer"),
            create_state(own_username="NewPlayer"),
            True,
        ),
        (
            create_state(),
            InitializeAsEvent("NewPlayer"),
            create_state(own_username="NewPlayer"),
            True,
        ),
        (
            create_state(
                party_members={"Player1", "Player2"}, lobby_players={"RandomPlayer"}
            ),
            LobbySwapEvent(),
            create_state(party_members={"Player1", "Player2"}),
            True,
        ),
        (
            create_state(),
            LobbyJoinEvent("Player1", player_count=2, player_cap=16),
            create_state(lobby_players={"Player1"}),
            True,
        ),
        (
            create_state(),
            LobbyJoinEvent("Player1", player_count=5, player_cap=16),
            create_state(lobby_players={"Player1"}, out_of_sync=True),
            True,
        ),
        (
            create_state(lobby_players={"Leaving"}),
            LobbyLeaveEvent("Leaving"),
            create_state(),
            True,
        ),
        (
            # The lobby is cleared and set to the received usernames
            # Your own username should always appear in the list
            create_state(lobby_players={"PersonFromLastLobby"}),  # Old members cleared
            LobbyListEvent([OWN_USERNAME, "Player1", "Player2"]),  # You always online
            create_state(lobby_players={"Player1", "Player2"}),
            True,
        ),
        (
            create_state(),
            PartyAttachEvent("Player2"),
            create_state(party_members={"Player2"}),
            True,
        ),
        (
            create_state(party_members={"Player1", "Player2"}),
            PartyDetachEvent(),
            create_state(),
            True,
        ),
        (
            create_state(party_members={"Player1", "Player2"}),
            PartyJoinEvent(["Player3", "Player4"]),
            create_state(party_members={"Player1", "Player2", "Player3", "Player4"}),
            True,
        ),
        (
            create_state(party_members={"Player1", "Player2", "Player3"}),
            PartyLeaveEvent(["Player3"]),
            create_state(party_members={"Player1", "Player2"}),
            True,
        ),
        (
            create_state(party_members={"Player1", "Player2", "Player3"}),
            PartyLeaveEvent(["Player3", "Player2"]),
            create_state(party_members={"Player1"}),
            True,
        ),
        (
            create_state(party_members={"Player1", "Player2", "Player3"}),
            PartyListIncomingEvent(),
            create_state(),
            False,
        ),
        (
            create_state(party_members={"Player3"}),
            PartyMembershipListEvent(
                usernames=["Player1", "Player2"], role="moderators"
            ),
            create_state(party_members={"Player1", "Player2", "Player3"}),
            True,
        ),
        # Special cases
        (
            # Party leave when own username is unknown
            create_state(party_members={"Player1", "Player2"}, own_username=None),
            PartyDetachEvent(),
            create_state(own_username=None),
            True,
        ),
        (
            # Lobby join when own username is unknown
            create_state(lobby_players={"Player1", "Player2"}, own_username=None),
            LobbySwapEvent(),
            create_state(own_username=None),
            True,
        ),
        (
            # Player not in party leaves party
            create_state(party_members={"Player1", "Player2"}),
            PartyLeaveEvent(["RandomPlayer"]),
            create_state(party_members={"Player1", "Player2"}),
            # TODO: False,
            True,
        ),
        (
            # Player not in lobby leaves lobby
            create_state(lobby_players={"Player1", "Player2"}),
            LobbyLeaveEvent("RandomPlayer"),
            create_state(lobby_players={"Player1", "Player2"}),
            # TODO: False,
            True,
        ),
        (
            # Small player cap -> not bedwars
            create_state(),
            LobbyJoinEvent("Player1", player_count=2, player_cap=2),
            create_state(),
            False,
        ),
    ),
)
def test_update_state(
    initial_state: OverlayState, event: Event, target_state: OverlayState, redraw: bool
) -> None:
    """Assert that remove_ranks functions properly"""
    will_redraw = update_state(initial_state, event)

    new_state = initial_state
    assert new_state == target_state
    assert will_redraw == redraw
