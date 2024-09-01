import pytest

from prism.overlay.state import OverlayState
from tests.prism.overlay.utils import create_state


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
