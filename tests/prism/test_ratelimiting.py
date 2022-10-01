import math
import unittest.mock
from collections.abc import Callable

import pytest

from prism.ratelimiting import RateLimiter
from tests.mock_utils import MockedTime


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
    # Init the ratelimiter at time t=0
    with unittest.mock.patch("prism.ratelimiting.time", MockedTime().time):
        limiter = RateLimiter(limit=limit, window=window)

    requests = sorted(make_requests(limiter))
    time_elapsed = requests[-1] - requests[0]

    # Guaranteed minimal amount of windows for the given amount of requests
    min_windows = math.ceil(len(requests) / limit) - 1
    min_time = min_windows * window

    # Correctness of the ratelimiter
    assert time_elapsed >= min_time, "Ratelimiter exceeded max throughput!"

    assert all(
        next_request - request >= window
        for request, next_request in zip(requests, requests[limit:])
    ), f"Requests are too close in time {requests}"


def test_ratelimiting_sequential() -> None:
    """Assert that RateLimiter functions under sequential operation"""
    window = 1
    limit = 10
    amt_requests = 21

    def make_requests(limiter: RateLimiter) -> list[float]:
        requests: list[float] = []
        for i in range(amt_requests):
            with unittest.mock.patch(
                "prism.ratelimiting.time", MockedTime().time
            ) as mocked_time_module, limiter:
                requests.append(mocked_time_module.monotonic())
        return requests

    time_ratelimiter(window, limit, make_requests)


def test_ratelimiting_parallell() -> None:
    """Assert that RateLimiter functions under parallell operation"""
    window = 1
    limit = 10
    amt_iterations = 10
    amt_threads = 16

    assert (
        amt_threads > limit
    ), "Tests the behaviour when a request completes in the next window"

    mocked_time_modules = [MockedTime().time for i in range(amt_threads)]

    # Simulate parallell operation by acquiring multiple limit slots at the same time
    def make_requests(limiter: RateLimiter) -> list[float]:
        requests: list[float] = []
        for i in range(amt_iterations):
            with unittest.mock.patch(
                "prism.ratelimiting.time", mocked_time_modules[0]
            ), limiter:
                requests.append(mocked_time_modules[0].monotonic())
                for inner_mocked_time_module in mocked_time_modules[1:]:
                    with unittest.mock.patch(
                        "prism.ratelimiting.time", inner_mocked_time_module
                    ), limiter:
                        requests.append(inner_mocked_time_module.monotonic())
        return requests

    time_ratelimiter(window, limit, make_requests)
