import sys

from tendo import singleton

from prism.overlay.directories import CACHE_DIR, must_ensure_directory

# Variable that stores our singleinstance lock so that it doesn't go out of scope
# and get released
SINGLEINSTANCE_LOCK = None


def ensure_not_parallel() -> None:
    """Ensure that only one instance of the overlay is running"""
    must_ensure_directory(CACHE_DIR)

    global SINGLEINSTANCE_LOCK
    try:
        SINGLEINSTANCE_LOCK = (
            singleton.SingleInstance(  # type: ignore [no-untyped-call]
                lockfile=str(CACHE_DIR / "prism_overlay.lock")
            )
        )
    except singleton.SingleInstanceException:  # pragma: no cover
        # TODO: Shown the running overlay window
        print(
            "You can only run one instance of the overlay at the time", file=sys.stderr
        )
        sys.exit(1)
