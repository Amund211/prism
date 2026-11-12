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


def test_team_map() -> None:
    assert create_state().team_map == {}
    state = create_state(player_teams=[("Player1", "red"), ("Player2", "blue")])
    assert state.team_map == {"Player1": "red", "Player2": "blue"}


def test_has_final_kills_or_deaths() -> None:
    assert create_state().has_final_kills_or_deaths is False
    in_sync = create_state(
        lobby_players={"Player1", "Player2"},
        alive_players={"Player1", "Player2"},
    )
    assert in_sync.has_final_kills_or_deaths is False
    final_kill = create_state(
        lobby_players={"Player1", "Player2"},
        alive_players={"Player1"},
    )
    assert final_kill.has_final_kills_or_deaths is True


def test_set_player_team() -> None:
    initial = create_state()
    s1 = initial.set_player_team("Player1", "red")
    assert s1.team_map == {"Player1": "red"}
    assert s1.player_teams == frozenset([("Player1", "red")])
    assert initial.team_map == {}

    # Overwrite with same casing
    s2 = s1.set_player_team("Player1", "blue")
    assert s2.team_map == {"Player1": "blue"}
    assert s2.player_teams == frozenset([("Player1", "blue")])

    # Overwrite with different casing
    s3 = s2.set_player_team("player1", "green")
    assert s3.team_map == {"player1": "green"}
    assert s3.player_teams == frozenset([("player1", "green")])

    # Remove with None (case-insensitive)
    s4 = s3.set_player_team("PLAYER1", None)
    assert s4.team_map == {}
    assert s4.player_teams == frozenset()

    # Remove with None when player does not exist
    s5 = initial.set_player_team("PlayerUnknown", None)
    assert s5.player_teams == frozenset()


def test_set_players_team() -> None:
    initial = create_state()
    s1 = initial.set_players_team(["Player1", "Player2"], "yellow")
    assert s1.team_map == {"Player1": "yellow", "Player2": "yellow"}
    assert s1.player_teams == frozenset([("Player1", "yellow"), ("Player2", "yellow")])

    # Clear via None
    s2 = s1.set_players_team(["Player1", "Player2"], None)
    assert s2.team_map == {}
    assert s2.player_teams == frozenset()


def test_clear_teams() -> None:
    state = create_state(player_teams=[("Player1", "red"), ("Player2", "blue")])
    cleared = state.clear_teams()
    assert cleared.player_teams == frozenset()
    assert cleared.team_map == {}


def test_set_lobby_preserves_lobby_and_party_teams() -> None:
    state = create_state(
        party_members={OWN_USERNAME, "PartyMate"},
        lobby_players={"Player1", "Player2", "OldPlayer", OWN_USERNAME, "PartyMate"},
        player_teams=[
            ("Player1", "red"),
            ("Player2", "blue"),
            ("OldPlayer", "green"),
            (OWN_USERNAME, "yellow"),
            ("PartyMate", "yellow"),
        ],
    )
    # New lobby has Player1 and NewPlayer (not Player2 or OldPlayer, nor party members)
    new_state = state.set_lobby(["Player1", "NewPlayer"])
    assert new_state.lobby_players == frozenset(["Player1", "NewPlayer"])
    assert new_state.alive_players == frozenset(["Player1", "NewPlayer"])
    assert new_state.team_map == {
        "Player1": "red",
        OWN_USERNAME: "yellow",
        "PartyMate": "yellow",
    }

    # Case-insensitive lobby match
    case_state = create_state(
        party_members={OWN_USERNAME},
        player_teams=[("Player1", "red")],
    )
    assert case_state.set_lobby(["player1"]).team_map == {"Player1": "red"}


def test_clear_lobby_clears_teams_even_with_party() -> None:
    state = create_state(
        party_members={OWN_USERNAME, "Player2"},
        lobby_players={OWN_USERNAME, "Player2", "Enemy"},
        alive_players={OWN_USERNAME, "Player2", "Enemy"},
        player_teams=[
            (OWN_USERNAME, "red"),
            ("Player2", "red"),
            ("Enemy", "blue"),
        ],
    )
    cleared = state.clear_lobby()
    assert cleared.lobby_players == frozenset()
    assert cleared.alive_players == frozenset()
    assert cleared.player_teams == frozenset()
    assert cleared.team_map == {}
    assert cleared.party_members == frozenset({OWN_USERNAME, "Player2"})


def test_leave_game_clears_teams() -> None:
    state = create_state(
        last_game_start=100.0,
        bedwars_duel="rush",
        player_teams=[("Player1", "red")],
    )
    left = state.leave_game()
    assert left.last_game_start is None
    assert left.bedwars_duel is None
    assert left.player_teams == frozenset()
    assert left.team_map == {}


def test_in_game() -> None:
    assert create_state(last_game_start=1.0).in_game is True
    assert create_state(last_game_start=None).in_game is False


def test_party_mutations() -> None:
    state = create_state(party_members={OWN_USERNAME})
    added = state.add_to_party("Player2")
    assert added.party_members == frozenset({OWN_USERNAME, "Player2"})
    removed = added.remove_from_party("Player2")
    assert removed.party_members == frozenset({OWN_USERNAME})
    # Remove player not in party
    assert removed.remove_from_party("NonExistent") == removed


def test_lobby_mutations() -> None:
    state = create_state().add_to_lobby("Player1")
    assert state.lobby_players == frozenset(["Player1"])
    assert state.alive_players == frozenset(["Player1"])


def test_mark_dead_and_alive() -> None:
    state = create_state(lobby_players={"Player1"}, alive_players={"Player1"})
    dead = state.mark_dead("Player1")
    assert dead.alive_players == frozenset()
    assert dead.lobby_players == frozenset(["Player1"])

    # Marking dead when not in alive_players adds to lobby_players
    missing = create_state(lobby_players=set(), alive_players=set())
    marked_missing = missing.mark_dead("Player2")
    assert marked_missing.lobby_players == frozenset(["Player2"])
    assert marked_missing.alive_players == frozenset()

    # Marking alive
    alive = dead.mark_alive("Player1")
    assert alive.alive_players == frozenset(["Player1"])
    # Already alive
    assert alive.mark_alive("Player1") == alive
    # Not in lobby
    not_in_lobby = create_state(lobby_players=set(), alive_players=set())
    alive_new = not_in_lobby.mark_alive("Player3")
    assert alive_new.alive_players == frozenset(["Player3"])
    assert alive_new.lobby_players == frozenset(["Player3"])


def test_join_and_leave_queue() -> None:
    # Dirty state from previous game
    dirty = create_state(
        party_members={OWN_USERNAME, "Player2"},
        lobby_players={OWN_USERNAME, "Player2", "OldEnemy"},
        alive_players={OWN_USERNAME, "Player2"},
    )
    queued = dirty.join_queue()
    assert queued.in_queue is True
    assert queued.lobby_players == frozenset({OWN_USERNAME, "Player2"})
    assert queued.alive_players == frozenset({OWN_USERNAME, "Player2"})

    # Clean lobby keeping lobby warning path
    clean = create_state(
        party_members={OWN_USERNAME},
        lobby_players={OWN_USERNAME, "Player3"},
        alive_players={OWN_USERNAME, "Player3"},
    )
    queued_clean = clean.join_queue()
    assert queued_clean.in_queue is True
    assert queued_clean.lobby_players == frozenset({OWN_USERNAME, "Player3"})

    # Leave queue
    assert queued.leave_queue().in_queue is False


def test_set_out_of_sync() -> None:
    state = create_state(out_of_sync=False)
    assert state.set_out_of_sync(True).out_of_sync is True
    assert state.set_out_of_sync(False) is state
