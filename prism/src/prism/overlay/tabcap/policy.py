"""When to take tab-list screenshots, and what to read from them"""

from prism.overlay.state import OverlayState

# Trial branch: delays after the Tab press. Dense at first, then once per
# second while Tab is held. The burst stops when Tab is released.
# 0 ms: before the game draws the list (seen at 30 ms at the earliest), so each
# burst has a frame of the same scene without the list (training data).
CAPTURE_DELAYS_MS = (0, 60, 120, 250, 500, 1000) + tuple(range(2000, 11000, 1000))
# No team read on these: no list yet, and a read (~1 s) would delay the next grabs
NO_READ_DELAYS_MS = frozenset({0})
# At most one burst per this many seconds
MIN_BURST_INTERVAL_SECONDS = 0.3


def known_names(state: OverlayState) -> list[str]:
    """Names the recognition can match rows against"""
    names = state.lobby_players | state.alive_players | state.party_members
    if state.own_username is not None:
        names |= {state.own_username}
    return sorted(names)


def should_start_burst(
    *, now: float, last_burst_start: float | None, busy: bool
) -> bool:
    """Return True if a Tab press at `now` should start a new burst"""
    if busy:
        return False
    if last_burst_start is None:
        return True
    return now - last_burst_start >= MIN_BURST_INTERVAL_SECONDS
