import math
import unittest.mock
from collections.abc import Callable

import pytest

from prism.ratelimiting import RateLimiter
from tests.mock_utils import MockedTime, _MockedTimeModule


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
    window: float,
    limit: int,
    make_requests: Callable[[RateLimiter, _MockedTimeModule], list[float]],
) -> None:
    """Assert that RateLimiter appropriately limits requests"""
    # Init the ratelimiter at time t=0
    with unittest.mock.patch(
        "prism.ratelimiting.time", MockedTime().time
    ) as mocked_time_module:
        limiter = RateLimiter(limit=limit, window=window)
        requests = sorted(make_requests(limiter, mocked_time_module))

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

    def make_requests(
        limiter: RateLimiter, mocked_time_module: _MockedTimeModule
    ) -> list[float]:
        requests: list[float] = []
        for i in range(amt_requests):
            with limiter:
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

    # Simulate parallell operation by acquiring multiple limit slots at the same time
    def make_requests(
        limiter: RateLimiter, mocked_time_module: _MockedTimeModule
    ) -> list[float]:
        requests: list[float] = []
        for i in range(amt_iterations):
            with limiter:
                requests.append(mocked_time_module.monotonic())
                for i in range(amt_threads - 1):
                    with limiter:
                        requests.append(mocked_time_module.monotonic())
        return requests

    time_ratelimiter(window, limit, make_requests)


def test_ratelimiting_multithreaded() -> None:
    """Assert that RateLimiter functions under multithreaded operation"""
    import queue
    import threading
    import time

    window = 1
    limit = 10
    amt_iterations = 10
    amt_threads = 32

    class PerformOperationThread(threading.Thread):
        def __init__(
            self,
            limiter: RateLimiter,
            mocked_time_module: _MockedTimeModule,
            requests_queue: queue.Queue[float],
            iterations: int,
        ) -> None:
            super().__init__()
            self.limiter = limiter
            self.mocked_time_module = mocked_time_module
            self.requests_queue = requests_queue
            self.iterations = iterations

        def run(self) -> None:
            for i in range(self.iterations):
                with self.limiter:
                    self.requests_queue.put_nowait(self.mocked_time_module.monotonic())
                    # Use real time.sleep to suspend execution in this thread
                    time.sleep(0.1 / (self.iterations * amt_threads))

    def make_requests(
        limiter: RateLimiter, mocked_time_module: _MockedTimeModule
    ) -> list[float]:
        requests_queue = queue.Queue[float]()
        requests: list[float] = []
        threads = [
            PerformOperationThread(
                limiter, mocked_time_module, requests_queue, amt_iterations
            )
            for i in range(amt_threads)
        ]
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        while True:
            try:
                request = requests_queue.get_nowait()
            except queue.Empty:
                break
            else:
                requests_queue.task_done()
                requests.append(request)

        requests_queue.join()

        return requests

    time_ratelimiter(window, limit, make_requests)


def test_ratelimiting_is_blocked() -> None:
    with unittest.mock.patch(
        "prism.ratelimiting.time", MockedTime().time
    ) as mocked_time_module:
        limiter = RateLimiter(limit=2, window=10)
        assert not limiter.is_blocked, "Not blocked to start with"

        limiter.__enter__()
        assert not limiter.is_blocked
        mocked_time_module.sleep(5)
        assert mocked_time_module.monotonic() == 5

        limiter.__enter__()
        assert limiter.is_blocked
        mocked_time_module.sleep(5)
        assert mocked_time_module.monotonic() == 10

        limiter.__exit__(None, None, None)
        assert limiter.is_blocked
        mocked_time_module.sleep(5)
        assert mocked_time_module.monotonic() == 15

        assert limiter.is_blocked
        mocked_time_module.sleep(5)
        assert mocked_time_module.monotonic() == 20

        assert not limiter.is_blocked
        mocked_time_module.sleep(5)
        assert mocked_time_module.monotonic() == 25
        limiter.__exit__(None, None, None)
        assert not limiter.is_blocked
