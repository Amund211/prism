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
    StartBedwarsGameEvent,
)
from examples.sidelay.state import OverlayState, update_state

OWN_USERNAME = "OwnUsername"


def create_state(
    party_members: set[str] = set(),
    lobby_players: set[str] = set(),
    out_of_sync: bool = False,
    in_queue: bool = False,
    own_username: Optional[str] = OWN_USERNAME,
) -> OverlayState:
    yourself = set() if own_username is None else set([own_username])
    return OverlayState(
        party_members=party_members | yourself,
        lobby_players=lobby_players | yourself,
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
        LobbyJoinEvent("Player1", player_count=2, player_cap=8),
        create_state(lobby_players={"Player1"}, in_queue=True),
        True,
    ),
    (
        "lobby join doubles/fours",
        create_state(),
        LobbyJoinEvent("Player1", player_count=2, player_cap=16),
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
        LobbyListEvent([OWN_USERNAME, "Player1", "Player2"]),  # You always online
        create_state(lobby_players={"Player1", "Player2"}, in_queue=True),
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
    # Special cases
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
        LobbyJoinEvent("Player1", player_count=2, player_cap=16),
        create_state(lobby_players={"Player1"}, in_queue=True),
        True,
    ),
    (
        # Player count too high -> clear lobby, still out of sync
        "too many known players in lobby, too few remaining",
        create_state(lobby_players={"PlayerA", "PlayerB"}, in_queue=True),
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
        create_state(lobby_players={"Player1"}, out_of_sync=True, in_queue=True),
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
