from dataclasses import dataclass

from prism.overlay.state import OverlayState


@dataclass(frozen=True, slots=True)
class Shown:
    """Show the overlay"""


@dataclass(frozen=True, slots=True)
class Hidden:
    """Hide the overlay after autohide_timeout"""


@dataclass(frozen=True, slots=True)
class ShownUntil:
    """Show the overlay, and hide it at `deadline` (time.monotonic)"""

    deadline: float


Visibility = Shown | Hidden | ShownUntil


def get_visibility(
    state: OverlayState, *, wants_shown: bool | None, autohide_timeout: int
) -> Visibility:
    """Return the target visibility of the overlay"""
    if wants_shown is not None:
        # The user has a preference -> honor it
        return Shown() if wants_shown else Hidden()

    if (
        state.bedwars_duel is not None
        and state.last_game_start is not None
        and not state.out_of_sync  # Cleared by a /who reply
    ):
        # Duels have no queue. Show after a /who reply, and hide at the same time
        # as a regular game.
        # NOTE: last_game_start is from OverlayState.now_func (time.monotonic)
        return ShownUntil(deadline=state.last_game_start + autohide_timeout)

    # Fall back to showing the overlay in queue and hiding it in game
    # TODO: Use ShownUntil(last_game_start + autohide_timeout) in regular games too,
    #       and use that deadline in the /who pin rule in process_event (LOBBY_LIST)
    return Shown() if state.in_queue else Hidden()
