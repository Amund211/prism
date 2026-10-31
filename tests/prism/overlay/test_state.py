from collections.abc import Callable

import pytest

from prism.overlay.server import Server
from prism.overlay.state import OverlayState
from tests.prism.overlay.utils import OWN_USERNAME, create_dirty_state, create_state

HYPIXEL = Server.from_host("mc.hypixel.net")
OTHER = Server.from_host("bedwarspractice.club")
SINGLEPLAYER = Server.singleplayer()


@pytest.mark.parametrize(
    "before, after",
    (
        (create_state(), create_state()),
        (create_state(party_members={"OwnUsername", "Player2"}), create_state()),
        (
            OverlayState(party_members=frozenset(), own_username="OwnUsername"),
            create_state(),
        ),
        (
            create_state(own_username=None, party_members=set()),
            create_state(own_username=None, party_members=set()),
        ),
    ),
)
def test_clear_party(before: OverlayState, after: OverlayState) -> None:
    assert before.clear_party() == after


@pytest.mark.parametrize(
    "state, time_in_game",
    (
        (create_state(), None),
        (create_state(last_game_start=0, now_func=lambda: 10), 10),
        (create_state(last_game_start=1234, now_func=lambda: 1234 + 12345), 12345),
    ),
)
def test_time_in_game(state: OverlayState, time_in_game: float | None) -> None:
    assert state.time_in_game == time_in_game


@pytest.mark.parametrize(
    "before, transition, after",
    (
        (
            create_state(now_func=lambda: 5),
            OverlayState.join_duel,
            create_state(last_game_start=5, bedwars_duel="unknown", now_func=lambda: 5),
        ),
        (
            create_state(last_game_start=1, bedwars_duel="rush", now_func=lambda: 5),
            OverlayState.join_game,
            create_state(last_game_start=5, now_func=lambda: 5),
        ),
        (
            create_state(last_game_start=1, bedwars_duel="unknown"),
            lambda state: state.set_bedwars_duel_type("regular"),
            create_state(last_game_start=1, bedwars_duel="regular"),
        ),
        (
            create_state(last_game_start=1, bedwars_duel="rush"),
            OverlayState.leave_game,
            create_state(),
        ),
    ),
)
def test_bedwars_duel_transitions(
    before: OverlayState,
    transition: Callable[[OverlayState], OverlayState],
    after: OverlayState,
) -> None:
    assert transition(before) == after


def test_join_queue_in_queue() -> None:
    # We avoid this case by checking in_queue before calling join_queue
    state = create_state(in_queue=True)
    assert state.join_queue() is state


@pytest.mark.parametrize(
    "state, expected",
    (
        (
            create_state(party_members={OWN_USERNAME, "A", "B", "C"}),
            {OWN_USERNAME, "A", "B", "C"},
        ),
        (
            create_state(
                party_members={OWN_USERNAME, "A", "B", "C"}, lobby_players={"A"}
            ),
            # TODO: Remove A
            {OWN_USERNAME, "A", "B", "C"},
        ),
        (
            create_state(
                party_members={OWN_USERNAME, "A", "B", "C"},
                lobby_players={"A"},
                alive_players=set(),
            ),
            # TODO: Remove A
            {OWN_USERNAME, "A", "B", "C"},
        ),
    ),
)
def test_missing_party_members(state: OverlayState, expected: set[str]) -> None:
    assert state.missing_party_members == expected


@pytest.mark.parametrize(
    "before, server, after",
    (
        # Active -> active keeps state (rejoin a game in progress)
        (create_dirty_state(), HYPIXEL, create_dirty_state(server=HYPIXEL)),
        (
            create_dirty_state(server=HYPIXEL),
            HYPIXEL,
            create_dirty_state(server=HYPIXEL),
        ),
        # Entering an inactive server clears all but the party
        *(
            (
                create_dirty_state(server=from_server),
                to_server,
                create_state(party_members={OWN_USERNAME, "Player2"}, server=to_server),
            )
            for from_server in (None, HYPIXEL, OTHER, SINGLEPLAYER)
            for to_server in (OTHER, SINGLEPLAYER)
        ),
        # Inactive -> active keeps the (already clean) state
        (
            create_state(server=OTHER),
            HYPIXEL,
            create_state(server=HYPIXEL),
        ),
    ),
)
def test_set_server(before: OverlayState, server: Server, after: OverlayState) -> None:
    assert before.set_server(server) == after


@pytest.mark.parametrize(
    "server, only_hypixel, active",
    (
        (None, True, True),
        (HYPIXEL, True, True),
        (Server.from_host("localhost"), True, True),
        (Server.from_host("1.2.3.4"), True, True),
        (OTHER, True, False),
        (SINGLEPLAYER, True, False),
        (OTHER, False, True),
        (SINGLEPLAYER, False, True),
    ),
)
def test_is_active(server: Server | None, only_hypixel: bool, active: bool) -> None:
    assert create_state(server=server).is_active(only_hypixel) == active
