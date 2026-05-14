import sys

from filelock import FileLock, Timeout

from prism.overlay.directories import CACHE_DIR, must_ensure_directory

# Variable that stores our singleinstance lock so that it doesn't go out of scope
# and get released
SINGLEINSTANCE_LOCK: FileLock | None = None


def ensure_not_parallel() -> None:
    """Ensure that only one instance of the overlay is running"""
    must_ensure_directory(CACHE_DIR)

    global SINGLEINSTANCE_LOCK
    lock = FileLock(str(CACHE_DIR / "prism_overlay.lock"), timeout=0)
    try:
        lock.acquire()
    except Timeout:  # pragma: no cover
        # TODO: Show the running overlay window
        print(
            "You can only run one instance of the overlay at the time", file=sys.stderr
        )
        sys.exit(1)
    SINGLEINSTANCE_LOCK = lock
