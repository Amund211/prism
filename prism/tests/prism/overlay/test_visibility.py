import pytest

from prism.overlay.state import OverlayState
from prism.overlay.visibility import (
    Hidden,
    Shown,
    ShownUntil,
    Visibility,
    get_visibility,
)
from tests.prism.overlay.utils import create_state


def duel_state(time_in_game: float, out_of_sync: bool = False) -> OverlayState:
    return create_state(
        last_game_start=100,
        out_of_sync=out_of_sync,
        bedwars_duel="rush",
        now_func=lambda: 100 + time_in_game,
    )


@pytest.mark.parametrize(
    "state, wants_shown, visibility",
    (
        # The user's preference wins
        (create_state(in_queue=True), False, Hidden()),
        (create_state(), True, Shown()),
        (duel_state(time_in_game=1), False, Hidden()),
        (duel_state(time_in_game=1), True, Shown()),
        # Show in queue, hide in game
        (create_state(in_queue=True), None, Shown()),
        (create_state(), None, Hidden()),
        (create_state(last_game_start=100, now_func=lambda: 101), None, Hidden()),
        # Duel: show after a /who reply until game start + autohide_timeout
        (duel_state(time_in_game=1, out_of_sync=True), None, Hidden()),
        (duel_state(time_in_game=3), None, ShownUntil(deadline=108)),
        (duel_state(time_in_game=100), None, ShownUntil(deadline=108)),
    ),
)
def test_get_visibility(
    state: OverlayState, wants_shown: bool | None, visibility: Visibility
) -> None:
    assert (
        get_visibility(state, wants_shown=wants_shown, autohide_timeout=8) == visibility
    )
