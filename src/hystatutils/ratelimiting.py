import threading
import time
from collections import deque
from datetime import datetime


class RateLimiter:
    """
    Thread-safe window/limit rate-limiting

    Ensures .wait() only returns `limit` times with in any `window` second
    time window across all threads.
    NOTE: Only calls to .wait() are rate-limited and, depending on the scheduler,
    further code may be executed later.
    """

    def __init__(self, limit: int, window: float):
        assert limit >= 1
        assert window > 0

        self.limit = limit
        self.window = window
        self.made_requests = deque([datetime.now()], maxlen=limit)
        self.mutex = threading.Lock()

    def wait(self) -> None:
        """Wait until the earliest request still in the window leaves the window"""
        # Block other threads from waiting while we wait
        with self.mutex:
            now = datetime.now()
            if len(self.made_requests) == self.limit:
                timespan = now - self.made_requests[0]
                if timespan.total_seconds() < self.window:
                    # Wait until the request has left the window
                    # Skip coverage checks as the coverage report may become flaky
                    time.sleep(
                        self.window - timespan.total_seconds()
                    )  # pragma: no cover

            self.made_requests.append(now)
