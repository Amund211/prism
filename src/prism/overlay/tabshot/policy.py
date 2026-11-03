"""When to take tab-list screenshots (phase 1: collect samples)"""

from collections.abc import Iterator

# Delays after the Tab press. Several, to find the best delay from data.
BURST_DELAYS_MS = (30, 60, 100, 200, 400)
HELD_INTERVAL_MS = 1000
MAX_HELD_CAPTURES = 5
# At most one burst per this many seconds
MIN_BURST_INTERVAL_SECONDS = 2.0


def burst_delays_ms() -> Iterator[int]:
    """Delays (ms after press) for the captures in one burst"""
    yield from BURST_DELAYS_MS
    for i in range(1, MAX_HELD_CAPTURES + 1):
        yield BURST_DELAYS_MS[-1] + i * HELD_INTERVAL_MS


def should_start_burst(
    *, now: float, last_burst_start: float | None, busy: bool
) -> bool:
    """Return True if a Tab press at `now` should start a new burst"""
    if busy:
        return False
    if last_burst_start is None:
        return True
    return now - last_burst_start >= MIN_BURST_INTERVAL_SECONDS
