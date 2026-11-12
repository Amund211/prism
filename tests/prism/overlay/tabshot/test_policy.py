import pytest

from prism.overlay.state import OverlayState
from prism.overlay.tabshot.policy import (
    CAPTURE_DELAYS_MS,
    known_names,
    should_start_burst,
)


def test_capture_delays_ms() -> None:
    # Dense at first, then once per second while Tab is held
    assert CAPTURE_DELAYS_MS[:5] == (60, 120, 250, 500, 1000)
    assert CAPTURE_DELAYS_MS[5:] == tuple(range(2000, 11000, 1000))
    assert list(CAPTURE_DELAYS_MS) == sorted(set(CAPTURE_DELAYS_MS))


def test_known_names() -> None:
    state = OverlayState(
        party_members=frozenset(("p",)),
        lobby_players=frozenset(("b", "a")),
        alive_players=frozenset(("a", "c")),
        own_username="me",
    )
    assert known_names(state) == ["a", "b", "c", "me", "p"]
    assert known_names(OverlayState()) == []


@pytest.mark.parametrize(
    "now, last_burst_start, busy, result",
    (
        (10.0, None, False, True),
        (10.0, None, True, False),
        (10.0, 9.8, False, False),
        (10.0, 9.5, False, True),
        (10.0, 7.0, True, False),
    ),
)
def test_should_start_burst(
    now: float, last_burst_start: float | None, busy: bool, result: bool
) -> None:
    assert (
        should_start_burst(now=now, last_burst_start=last_burst_start, busy=busy)
        is result
    )
