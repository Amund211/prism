from dataclasses import dataclass

from prism.overlay.state import OverlayState


@dataclass(frozen=True, slots=True)
class Shown:
    """Show the overlay"""


@dataclass(frozen=True, slots=True)
class Hidden:
    """Hide the overlay after autohide_timeout"""


Visibility = Shown | Hidden


def get_visibility(state: OverlayState, *, wants_shown: bool | None) -> Visibility:
    """Return the target visibility of the overlay"""
    if wants_shown is not None:
        # The user has a preference -> honor it
        return Shown() if wants_shown else Hidden()

    # Fall back to showing the overlay in queue and hiding it in game
    return Shown() if state.in_queue else Hidden()
