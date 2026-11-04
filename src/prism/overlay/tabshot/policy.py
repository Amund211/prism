"""When to take tab-list screenshots, and what to read from them"""

from collections.abc import Mapping

from prism.overlay.state import OverlayState

# Delays after the Tab press. The second capture is a retry, taken only if the
# first gave no teams and Tab is still held.
CAPTURE_DELAYS_MS = (150, 300)
# At most one burst per this many seconds
MIN_BURST_INTERVAL_SECONDS = 2.0


def should_retry(teams: Mapping[str, str]) -> bool:
    """Return True if we should capture again after this result"""
    return not teams


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
