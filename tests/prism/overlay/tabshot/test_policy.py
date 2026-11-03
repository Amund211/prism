import pytest

from prism.overlay.tabshot.policy import burst_delays_ms, should_start_burst


def test_burst_delays_ms() -> None:
    assert list(burst_delays_ms()) == [
        30,
        60,
        100,
        200,
        400,
        1400,
        2400,
        3400,
        4400,
        5400,
    ]


@pytest.mark.parametrize(
    "now, last_burst_start, busy, result",
    (
        (10.0, None, False, True),
        (10.0, None, True, False),
        (10.0, 9.0, False, False),
        (10.0, 8.0, False, True),
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
