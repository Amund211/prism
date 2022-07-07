import math
import time
from collections.abc import Callable

import pytest

from prism.ratelimiting import RateLimiter


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


def time_ratelimiter(
    window: float, limit: int, make_requests: Callable[[RateLimiter], list[float]]
) -> None:
    """Assert that RateLimiter appropriately limits requests"""
    limiter = RateLimiter(limit=limit, window=window)

    before = time.monotonic()
    requests = make_requests(limiter)
    after = time.monotonic()
    time_elapsed = after - before

    # Guaranteed minimal amount of windows for the given amount of requests
    min_windows = math.ceil(len(requests) / limit) - 1
    min_time = min_windows * window

    # Correctness of the ratelimiter - the limiter should not wait too little
    # The following two checks must pass, regardless of environment
    assert time_elapsed >= min_time, "Ratelimiter exceeded max throughput"

    # Assert that requests that are in different windows are at least `window` apart
    for request, next_request in zip(requests, requests[limit:]):
        assert next_request - request >= window

    # Optimality of the ratelimiter - the limiter should not wait too long
    # Elapsed time should be min_windows * window + overhead
    # Overhead should be < window on reasonably fast systems
    max_time = min_time + window
    if time_elapsed > max_time:
        pytest.skip(
            f"Ratelimiter is slower than expected!!! {time_elapsed=} > {max_time=}"
        )


def test_ratelimiting_sequential() -> None:
    """Assert that RateLimiter functions under sequential operation"""
    window = 0.04
    limit = 10
    amt_requests = 21

    def make_requests(limiter: RateLimiter) -> list[float]:
        requests: list[float] = []
        for i in range(amt_requests):
            with limiter:
                requests.append(time.monotonic())
        return requests

    time_ratelimiter(window, limit, make_requests)


def test_ratelimiting_parallell() -> None:
    """Assert that RateLimiter functions under parallell operation"""
    window = 0.04
    limit = 10
    amt_iterations = 11

    # Simulate parallell operation by acquiring multiple limit slots at the same time
    def make_requests(limiter: RateLimiter) -> list[float]:
        requests: list[float] = []
        for i in range(amt_iterations):
            with limiter:
                requests.append(time.monotonic())
                with limiter:
                    requests.append(time.monotonic())
                with limiter:
                    requests.append(time.monotonic())
        return requests

    time_ratelimiter(window, limit, make_requests)
