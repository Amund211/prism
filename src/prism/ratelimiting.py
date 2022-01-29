import threading
import time
from collections import deque
from datetime import datetime, timedelta
from itertools import repeat
from types import TracebackType
from typing import Optional

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
        old_timestamp = datetime.now() - timedelta(seconds=window)
        self.made_requests = deque(repeat(old_timestamp, limit))

    def __enter__(self) -> None:
        """
        Get the oldest request within the limit and wait for it to leave the window

        Blocks other threads from waiting simultaneously by acquiring the lock.
        """
        # Make sure there is data in the request history
        self.available_slots.acquire()

        with self.mutex:
            old_request = self.made_requests.popleft()

        now = datetime.now()
        time_since_request = now - old_request
        remaining_time_in_window = self.window - time_since_request.total_seconds()
        if remaining_time_in_window > 0:  # pragma: no cover
            # Wait until the old request has left the window
            time.sleep(remaining_time_in_window)

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        now = datetime.now()
        with self.mutex:
            # Insert the newly completed request in sorted order so that we don't
            # wait for it unnecessarily.
            insort_right(self.made_requests, now)

        # Tell the other threads that we added an element to the history
        self.available_slots.release()
