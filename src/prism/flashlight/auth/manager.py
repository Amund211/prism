import logging
import random
import threading
import time
from collections.abc import Callable
from typing import Protocol

from prism.flashlight.auth.errors import (
    AuthError,
    RefreshRateLimitedError,
    SessionExpiredError,
)
from prism.flashlight.auth.session import Session

logger = logging.getLogger(__name__)

# How long a flashlight request waits for a session before giving up.
#
# Every prism request carries a bearer, so this is also how long a request can
# block when we have no session - including the denick dialog's, which runs on
# the tkinter thread. It is far more than the two round trips a login needs, so
# it only bites during an outage, and then it bounds the freeze to something a
# user reads as "slow" rather than "hung".
SESSION_WAIT_TIMEOUT_SECONDS = 10.0

# Backoff for failed auth attempts. One curve for every cause, including the
# ones we cannot fix (an algorithm we don't implement, a difficulty we refuse):
# retrying those every few minutes costs nothing, and it means a server-side fix
# recovers every running overlay on its own, with no restart.
INITIAL_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 300.0
BACKOFF_MULTIPLIER = 2.0

# How long to wait after flashlight rate limited a refresh. The session is
# untouched, so we keep using it and stop asking for a while.
RATE_LIMITED_REFRESH_DELAY_SECONDS = 300.0


class LoginMethod(Protocol):  # pragma: nocover
    """
    A way to establish a brand new session

    The one tier-specific piece of the whole flow. Refreshing, scheduling,
    waiting and the 401 path all work off a `Session` alone, so a second tier
    (Microsoft) is a second implementation of this protocol and nothing else.
    """

    @property
    def tier(self) -> str:
        """The name of the tier this logs in to, for logging"""

    def log_in(self) -> Session:
        """Establish a new session, or raise `AuthError`"""


# Extends the given session. Tier-agnostic - the server branches on the stored
# session, not on the caller.
RefreshSession = Callable[[str], Session]


def _default_jitter() -> float:  # pragma: nocover
    return random.uniform(0.75, 1.25)


class AuthManager:
    """
    Owns prism's flashlight auth session

    There is exactly one writer: the auth thread. Every login and every refresh
    happens there, so we get single-flight structurally rather than by getting a
    lock protocol right - which matters, because up to 16 stats threads share the
    one bearer and they all see a 401 together when a session lapses.

    Request threads only ever:

    - read a snapshot, waiting for one to exist (`wait_for_session`)
    - report that a snapshot got a 401 (`recover_from_unauthorized`)
    - report that the server asked for a refresh (`note_refresh_hint`)

    A `Session` is immutable and replaced wholesale, so "did anything change?" is
    an identity comparison, which is what the 401 path uses to tell "your session
    was renewed, try again" from "we have nothing for you".
    """

    def __init__(
        self,
        *,
        login_method: LoginMethod,
        refresh_session: RefreshSession,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = _default_jitter,
    ) -> None:
        self._login_method = login_method
        self._refresh_session = refresh_session
        self._monotonic = monotonic
        self._jitter = jitter

        self._condition = threading.Condition()

        # Everything below is guarded by self._condition
        self._session: Session | None = None
        # Number of completed reconcile passes. Bumped exactly once per pass,
        # whatever the outcome, so a waiter can tell "the auth thread has looked
        # at this" from "nothing has happened yet".
        self._passes = 0
        # Monotonic deadline for the auth thread's next pass. Now, initially:
        # we have no session and want one.
        self._next_action_at = monotonic()
        # Monotonic deadline before which a *request* may not ask for a pass.
        # Only a failure moves it, and it is what stops 16 stats threads from
        # each queueing another login attempt while auth is broken - the auth
        # thread's own backoff would otherwise be bypassed on every 401.
        self._retry_not_before = monotonic()
        self._reconcile_requested = False
        self._backoff_seconds = INITIAL_BACKOFF_SECONDS
        self._consecutive_failures = 0
        self._last_error: str | None = None

    @property
    def consecutive_failures(self) -> int:
        """How many auth attempts have failed in a row"""
        with self._condition:
            return self._consecutive_failures

    @property
    def last_error(self) -> str | None:
        """Why the last auth attempt failed, if it did"""
        with self._condition:
            return self._last_error

    def start(self) -> None:  # pragma: nocover
        """Start the auth thread, which establishes and maintains the session"""
        threading.Thread(target=self._run, daemon=True, name="prism-auth").start()

    def _run(self) -> None:  # pragma: nocover
        while True:
            try:
                self.wait_for_work()
                self.reconcile()
            except Exception:
                # Every flashlight request needs this thread, so it must not be
                # possible for a bug in here to take the overlay down with it.
                logger.exception("Unexpected error in the auth thread")
                # TODO: This sleep outlives the retry deadline that is supposed to
                #       cover it. `reconcile`'s `except BaseException` calls `_fail`,
                #       which sets `_retry_not_before` to the *current* backoff (2s
                #       on the first failure), but we then sleep 300s. In between,
                #       every 401'd request queues a pass and blocks the full
                #       `SESSION_WAIT_TIMEOUT_SECONDS` waiting for a pass that
                #       cannot come - including `set_nickname` -> `get_uuid` on the
                #       tkinter thread, which is the frozen window that timeout
                #       exists to bound. Sleep the current backoff instead, or have
                #       `_fail` cover the sleep.
                time.sleep(MAX_BACKOFF_SECONDS)

    def wait_for_session(
        self, timeout: float = SESSION_WAIT_TIMEOUT_SECONDS
    ) -> Session | None:
        """
        Return the session to use, waiting up to `timeout` for one to exist

        None means we have no session and could not get one in time. The auth
        thread keeps trying in the background, so the next request may well
        succeed.
        """
        deadline = self._monotonic() + timeout
        with self._condition:
            while self._session is None:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            return self._session

    def recover_from_unauthorized(
        self, observed: Session, timeout: float = SESSION_WAIT_TIMEOUT_SECONDS
    ) -> Session | None:
        """
        Handle a 401 for `observed` and return a session to retry it with

        `None` means we have nothing to offer - a failed re-login, a timed-out
        wait, a backoff - and is never a verdict on the 401. Only the server
        gives one, on the 401 itself, in `X-Auth-Session`.
        """
        deadline = self._monotonic() + timeout
        with self._condition:
            if observed is not self._session:
                # Already replaced, by the auth thread's own timer or by another
                # request's 401. Retry with what we have now - no server call.
                # `None` here means it was replaced by nothing, i.e. discarded as
                # dead.
                # TODO: Returning `None` here makes a fan-out of 401s fail outright
                #       while the re-login it triggered is still in flight.
                #       `self._session` is None for the whole login after `_discard`
                #       (challenge + proof-of-work + login = two round trips), so
                #       every other thread gets nothing back and raises
                #       `SessionRecoveryError` immediately. Concretely: a laptop
                #       resumes from suspend - `time.monotonic()` does not advance
                #       across suspend, so we still believe the session is fresh
                #       while the server has expired it - the user opens a lobby, up
                #       to 16 stats threads 401 together, and the whole lobby
                #       renders as errors even though a valid session lands a second
                #       later. `wait_for_session` would have waited; this path does
                #       not. Fall through to the wait loop below when
                #       `self._session is None`.
                return self._session

            if self._monotonic() < self._retry_not_before:
                # Auth is failing, or flashlight has just rate limited us. Either
                # way: don't queue an attempt per request, and don't make the
                # caller wait for one.
                return None

            target = self._passes + 1
            self._reconcile_requested = True
            self._condition.notify_all()

            while self._passes < target:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    # Timed out waiting for the pass, so we have nothing to offer.
                    return None
                self._condition.wait(remaining)

            current = self._session
            return current if current is not observed else None

    def note_refresh_hint(self, session: Session) -> None:
        """
        Act on the server's `X-Auth-Refresh` hint for `session`

        A hint, never load-bearing: ignoring it stays correct and the reactive
        401 path remains the guarantee. It is the one mechanism that lets
        flashlight retune refresh timing for clients already in users' hands, so
        it is worth obeying.
        """
        with self._condition:
            if session is not self._session:
                return
            if self._monotonic() < self._retry_not_before:
                # Same reason as in recover_from_unauthorized: a fan-out of
                # responses must not out-vote the auth thread's backoff.
                return
            # TODO: Unfloored, unlike the proactive timer. A server hinting on
            #       every response gets one refresh per response wave forever -
            #       the too-soon 429 used to bound that.
            self._reconcile_requested = True
            self._condition.notify_all()

    def seconds_until_next_action(self) -> float:
        """Return how long the auth thread should idle before its next pass"""
        with self._condition:
            if self._reconcile_requested:
                return 0.0
            return max(0.0, self._next_action_at - self._monotonic())

    def wait_for_work(self) -> None:  # pragma: nocover
        """Block until there is auth work to do"""
        while True:
            delay = self.seconds_until_next_action()
            if delay <= 0:
                return
            with self._condition:
                # Re-checked under the lock, since the delay above was computed
                # without it. A stale delay only costs another loop, because
                # every wait is bounded.
                if self._reconcile_requested:
                    return
                self._condition.wait(delay)

    def reconcile(self) -> None:
        """
        Bring the session up to date: log in, or refresh what we hold

        Only the auth thread may call this - it is the single writer. Performs
        the network work outside the lock, then publishes the outcome.
        """
        with self._condition:
            session = self._session

        try:
            new_session = self._acquire(session)
        except RefreshRateLimitedError:
            # The session is untouched and still good. Keeping it is the whole
            # point: logging in again would throw away a session that works, and
            # spend the login limiter to do it.
            logger.warning(
                "Flashlight rate limited our session refresh. "
                "Keeping the session we have and trying again later."
            )
            self._postpone(RATE_LIMITED_REFRESH_DELAY_SECONDS)
        except AuthError as e:
            logger.warning("Failed establishing a flashlight auth session", exc_info=e)
            self._fail(str(e))
        except BaseException as e:
            # A bug rather than an auth failure. Record it as a failure anyway,
            # which publishes the pass and sets a retry deadline: without the
            # deadline every request would go on paying the full session wait for
            # a pass that cannot come while the auth thread sleeps this off.
            logger.exception("Unexpected error while reconciling the auth session")
            self._fail(f"unexpected error: {e!r}")
            raise
        else:
            logger.info(
                f"Established flashlight auth session "
                f"(tier={new_session.tier}, can_refresh={new_session.can_refresh})"
            )
            self._succeed(new_session)

    def _acquire(self, session: Session | None) -> Session:
        """Return a usable session, refreshing the one we hold when we can"""
        if session is None:
            logger.info(f"Logging in to flashlight ({self._login_method.tier})")
            return self._login_method.log_in()

        if not session.can_refresh:
            # The server said at issue time that refreshing this one again would
            # be pointless, so don't spend a round trip finding that out.
            logger.info("Session cannot be refreshed again - logging in")
            return self._login_method.log_in()

        try:
            return self._refresh_session(session.session_id)
        except SessionExpiredError:
            logger.info("Session is no longer refreshable - logging in")
            # Drop it before trying to log in, so that if the login also fails we
            # aren't left handing a token we know is dead to every request.
            # Validating an unknown bearer costs flashlight an uncached
            # transaction, so hammering it with one is not a neutral act.
            self._discard(session)
            return self._login_method.log_in()

    def _discard(self, session: Session) -> None:
        """Stop handing out a session we know flashlight will not accept"""
        with self._condition:
            if session is self._session:
                self._session = None

    def _succeed(self, session: Session) -> None:
        with self._condition:
            self._session = session
            # The one place a duration becomes a deadline, against the one clock
            # this class owns.
            self._next_action_at = self._monotonic() + session.refresh_in_seconds
            self._retry_not_before = self._monotonic()
            self._backoff_seconds = INITIAL_BACKOFF_SECONDS
            self._consecutive_failures = 0
            self._last_error = None
            self._finish_pass()

    def _postpone(self, delay: float) -> None:
        """
        Nothing changed - come back later

        **Never earlier than what was already scheduled.** The session we are
        holding is good until its own refresh point, and a rate limited refresh
        says nothing about that; moving the next attempt *forward* to `delay`
        would only spend more of the limit we have already hit.

        Requests are held off for `delay` too: asking again per 401 would only
        reproduce the same rate limit.
        """
        with self._condition:
            retry_at = self._monotonic() + delay
            self._next_action_at = max(retry_at, self._next_action_at)
            # TODO: This blocks the only path that can replace a session that
            #       really is dead, and nothing logs in instead - login is a
            #       different limiter and does not present the session.
            self._retry_not_before = retry_at
            self._finish_pass()

    def _fail(self, error: str) -> None:
        with self._condition:
            retry_at = self._monotonic() + self._backoff_seconds * self._jitter()
            self._next_action_at = retry_at
            self._retry_not_before = retry_at
            self._backoff_seconds = min(
                self._backoff_seconds * BACKOFF_MULTIPLIER, MAX_BACKOFF_SECONDS
            )
            self._consecutive_failures += 1
            self._last_error = error
            self._finish_pass()

    def _finish_pass(self) -> None:
        """Publish the outcome of a reconcile pass. Caller holds the condition."""
        # Cleared here, at the *end* of the pass. A request that reported a 401 or
        # a refresh hint while this pass was in flight has already been served by
        # it - the pass read the very session it is reporting about - so leaving
        # the flag set would make the auth thread immediately reconcile again.
        # Right after a successful refresh that second pass renews what was just
        # renewed, and every bearer response carries `X-Auth-Refresh` from exactly
        # the moment our own timer fires, so a lobby fan-out sets the flag every
        # single time.
        self._reconcile_requested = False
        self._passes += 1
        self._condition.notify_all()
