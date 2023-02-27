import threading
import time
from collections import deque
from itertools import repeat
from types import TracebackType

from prism.utils import insort_right


class RateLimiter:
    """
    Thread-safe window/limit rate-limiting contextmanager

    Ensures any operation within the context only occurs `limit` times
    within any `window` second time window across all threads.
    """

    def __init__(self, limit: int, window: float):
        assert limit >= 1
        assert window > 0

        self.limit = limit
        self.window = window
        self.mutex = threading.Lock()
        # Semaphore counting the remaining slots for concurrent execution
        # In practice this is the length of self.made_requests
        self.available_slots = threading.BoundedSemaphore(limit)

        # Fill the request history with placeholder data so we can assume that
        # the deque is non-empty when we have acquired self.avaliable_slots
        old_timestamp = time.monotonic() - window
        self.made_requests = deque(repeat(old_timestamp, limit))

    def __enter__(self) -> None:
        """
        Get the oldest request within the limit and wait for it to leave the window
        """
        # Make sure there is data in the request history
        self.available_slots.acquire()

        with self.mutex:
            old_request = self.made_requests.popleft()

        wait = self._compute_wait(old_request)
        if wait > 0:
            # Wait until the old request has left the window
            time.sleep(wait)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        now = time.monotonic()
        with self.mutex:
            # Insert the newly completed request in sorted order so that we don't
            # wait for it unnecessarily.
            insort_right(self.made_requests, now)

        # Tell the other threads that we added an element to the history
        self.available_slots.release()

    def _compute_wait(self, old_request: float) -> float:
        now = time.monotonic()
        time_since_request = now - old_request
        remaining_time_in_window = self.window - time_since_request

        return remaining_time_in_window

    @property
    def is_blocked(self) -> bool:
        """Return True if a request made at this time would have to wait"""
        with self.mutex:
            if len(self.made_requests) == 0:
                # We have to wait for a request to finish
                return True

            old_request = self.made_requests[0]

        return self._compute_wait(old_request) > 0
