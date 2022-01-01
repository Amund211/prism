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


def test_ratelimiting_sequential() -> None:
    """Assert that RateLimiter does not raise an exc under sequential operation"""
    limit = 10
    window = 0.05
    limiter = RateLimiter(limit=limit, window=window)
    for i in range(limit):
        with limiter:
            pass


def test_ratelimiting_parallell() -> None:
    """Assert that RateLimiter does not raise an exc under parallell operation"""
    limit = 10
    window = 0.05
    limiter = RateLimiter(limit=limit, window=window)
    for i in range(limit // 2):
        # Simulate parallell operation by acquiring two limit slots at the same time
        with limiter:
            with limiter:
                pass
