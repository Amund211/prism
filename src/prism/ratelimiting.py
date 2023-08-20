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
        self.made_requests = deque(repeat(old_timestamp, limit), maxlen=limit)
        self.grabbed_slots = deque(repeat(old_timestamp, limit), maxlen=limit + 1)

    def __enter__(self) -> None:
        """
        Get the oldest request within the limit and wait for it to leave the window
        """
        # Make sure there is data in the request history
        self.available_slots.acquire()

        with self.mutex:
            old_request = self.made_requests.popleft()
            insort_right(self.grabbed_slots, old_request)
            self.grabbed_slots.popleft()

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
        """
        Return True if a request is currently waiting

        NOTE: Only considers grabbed slots (i.e. slots for which a thread is sleeping)
              Does not return True when a thread is waiting to acquire a slot
        """
        with self.mutex:
            latest_inflight_request = self.grabbed_slots[-1]

        return self._compute_wait(latest_inflight_request) > 0

    @property
    def block_duration_seconds(self) -> float:
        """
        Return the shortest wait time left among all threads currently waiting

        Returns 0 if no threads are waiting

        NOTE: Returns 0 when there are no slots available
        """
        smallest_wait: float = 0

        with self.mutex:
            now = time.monotonic()
            for request in reversed(self.grabbed_slots):
                wait = request + self.window - now
                if wait <= 0:
                    return smallest_wait
                smallest_wait = wait

        # Unreachable. For a slot to be grabbed, one must be free, and thus have 0 wait
        return smallest_wait  # pragma: no coverage
