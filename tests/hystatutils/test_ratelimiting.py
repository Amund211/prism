import pytest

from hystatutils.ratelimiting import RateLimiter


@pytest.mark.parametrize(
    "limit, window",
    (
        (10, 0),
        (10, -1),
        (0, 1),
        (-1, 1),
        (-1, 0),
    ),
)
def test_ratelimiting_parameters(limit: int, window: float) -> None:
    """Assert that parameters to RateLimiter are validated"""
    with pytest.raises(AssertionError):
        RateLimiter(limit=limit, window=window)


def test_ratelimiting() -> None:
    """Assert that RateLimiter does not raise an exc under normal operation"""
    limit = 10
    window = 0.05
    limiter = RateLimiter(limit=limit, window=window)
    for i in range(limit):
        limiter.wait()
