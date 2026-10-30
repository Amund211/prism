import pytest

from prism.overlay.state import OverlayState
from prism.overlay.visibility import Hidden, Shown, Visibility, get_visibility
from tests.prism.overlay.utils import create_state


@pytest.mark.parametrize(
    "state, wants_shown, visibility",
    (
        # The user's preference wins
        (create_state(in_queue=True), False, Hidden()),
        (create_state(), True, Shown()),
        # Show in queue, hide in game
        (create_state(in_queue=True), None, Shown()),
        (create_state(), None, Hidden()),
        (create_state(last_game_start=100, now_func=lambda: 101), None, Hidden()),
    ),
)
def test_get_visibility(
    state: OverlayState, wants_shown: bool | None, visibility: Visibility
) -> None:
    assert get_visibility(state, wants_shown=wants_shown) == visibility
