"""Helpers for testing code that needs a flashlight auth session"""

import contextlib
import itertools
import threading
import time
from collections.abc import Callable, Iterator, Sequence

from prism.flashlight.auth.manager import AuthManager
from prism.flashlight.auth.session import Session

# Not a real session id - flashlight's are `flsess_` plus 32 random bytes
TEST_SESSION_ID = "flsess_test_session_id"


def make_session(
    *,
    session_id: str = TEST_SESSION_ID,
    tier: str = "anonymous",
    can_refresh: bool = True,
    refresh_in_seconds: float = 3300.0,
) -> Session:
    return Session(
        session_id=session_id,
        tier=tier,
        can_refresh=can_refresh,
        refresh_in_seconds=refresh_in_seconds,
    )


class QueuedLoginMethod:
    """A `LoginMethod` returning (or raising) queued results, in order"""

    tier = "test"

    def __init__(self, results: Sequence[Session | Exception] = ()) -> None:
        self.results = list(results)
        self.calls = 0

    def log_in(self) -> Session:
        self.calls += 1
        assert self.results, "Unexpected call to log_in"
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class QueuedRefresh:
    """A refresh callable returning (or raising) queued results, in order"""

    def __init__(self, results: Sequence[Session | Exception] = ()) -> None:
        self.results = list(results)
        self.session_ids: list[str] = []

    def __call__(self, session_id: str) -> Session:
        self.session_ids.append(session_id)
        assert self.results, "Unexpected call to refresh"
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_auth_manager(
    *,
    login_results: Sequence[Session | Exception] = (),
    refresh_results: Sequence[Session | Exception] = (),
    monotonic: Callable[[], float] | None = None,
) -> tuple[AuthManager, QueuedLoginMethod, QueuedRefresh]:
    """
    Return an `AuthManager` with a frozen clock and no jitter

    The auth thread is not started - tests drive `reconcile` themselves, which is
    also how the manager is meant to be reasoned about: a single writer taking one
    step at a time.

    Pass `monotonic=time.monotonic` for the few tests that need time to pass.
    """
    login_method = QueuedLoginMethod(login_results)
    refresh = QueuedRefresh(refresh_results)
    manager = AuthManager(
        login_method=login_method,
        refresh_session=refresh,
        monotonic=(lambda: 0.0) if monotonic is None else monotonic,
        jitter=lambda: 1.0,
    )
    return manager, login_method, refresh


def make_real_clock_auth_manager() -> AuthManager:
    """Return an `AuthManager` on the real clock, holding no session"""
    manager, _, _ = make_auth_manager(monotonic=time.monotonic)
    return manager


def make_fast_forward_auth_manager() -> AuthManager:
    """
    Return an `AuthManager` whose clock jumps, so every wait times out at once

    NOTE: The frozen clock in `make_auth_manager` must never be made to wait -
    the manager's wait loops recompute how much of the timeout is left from the
    clock, so a clock that never advances never reaches the deadline. Real
    monotonic clocks always advance; this is purely a test concern.
    """
    clock = itertools.count(0.0, 100.0)
    manager, _, _ = make_auth_manager(monotonic=lambda: next(clock))
    return manager


@contextlib.contextmanager
def running_auth_thread(manager: AuthManager) -> Iterator[list[BaseException]]:
    """
    Stand in for the auth thread, reconciling whenever it is asked to

    Only usable once the manager already holds a session - otherwise it would
    reconcile in a loop, since a manager with no session always wants one.

    Yields the list of exceptions reconcile raised. Swallowing them mirrors the
    real thread, which must survive a bug rather than take the overlay with it.
    """
    stop = threading.Event()
    errors: list[BaseException] = []

    def run() -> None:
        while not stop.is_set():
            if manager.seconds_until_next_action() <= 0:
                try:
                    manager.reconcile()
                except Exception as e:
                    errors.append(e)
                    return
            else:
                time.sleep(0.001)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield errors
    finally:
        stop.set()
        thread.join(timeout=5)
        assert not thread.is_alive()


def make_authenticated_manager() -> AuthManager:
    """Return an `AuthManager` holding a session, for tests that just need one"""
    manager, _, _ = make_auth_manager(login_results=[make_session()])
    manager.reconcile()
    return manager


def make_unauthenticated_manager() -> AuthManager:
    """Return an `AuthManager` that must never be asked for a session"""
    manager, _, _ = make_auth_manager()
    return manager
