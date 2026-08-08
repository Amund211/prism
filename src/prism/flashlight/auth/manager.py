import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from prism.flashlight.auth.errors import (
    AuthError,
    RefreshTooSoonError,
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

# How long to wait after the server says we refreshed too recently. No honest
# client should ever see this - we refresh 55 minutes into a 1 hour session and
# the server's floor is 30 minutes - so it is logged as the bug signal it is.
# The session is untouched, so we keep using it.
TOO_SOON_REFRESH_DELAY_SECONDS = 300.0


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


@dataclass(frozen=True, slots=True)
class Recovery:
    """
    What can be done about a request that got a 401

    The two fields are not redundant, and the difference is what keeps a valid
    Urchin API key from being blamed for an auth problem. `/v1/tags/{uuid}`
    answers 401 both for a bad key and for a session flashlight won't accept, so
    a caller may only interpret a 401 as its own when we can say the session is
    not the cause.
    """

    # A session to retry the request with, if we got one. Note refresh does not
    # rotate the id, so this can carry the same token with later deadlines.
    session: Session | None

    # True only when the *server* told us the session is fine - it refused to
    # replace one it considers too fresh. Then the 401 was about something else,
    # and the caller is the one that can interpret it. False whenever we could not
    # get a verdict, which includes a failed re-login and a timed-out wait: a
    # caller must not blame anything of its own for a 401 we cannot account for.
    session_confirmed: bool


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
    was renewed, try again" from "your session is fine, that 401 was about
    something else".
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
        # Whether the last pass ended with the server vouching for the session we
        # hold. Read by recover_from_unauthorized - see `Recovery`.
        self._last_pass_confirmed_session = False
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
    ) -> "Recovery":
        """
        Handle a 401 for `observed` and report what can be done about it

        See `Recovery`: either there is a session to retry with, or the server has
        confirmed the one we hold is fine (so the 401 was about something else), or
        we simply do not know.
        """
        deadline = self._monotonic() + timeout
        with self._condition:
            if observed is not self._session:
                # Already replaced, by the auth thread's own timer or by another
                # request's 401. Retry with what we have now - no server call.
                # `None` here means it was replaced by nothing, i.e. discarded as
                # dead, which is not a verdict on this 401.
                return Recovery(session=self._session, session_confirmed=False)

            if self._monotonic() < self._retry_not_before:
                # Auth is failing, or the server has just refused to touch this
                # session. Either way: don't queue an attempt per request, and
                # don't make the caller wait for one.
                return Recovery(
                    session=None,
                    session_confirmed=self._last_pass_confirmed_session,
                )

            target = self._passes + 1
            self._reconcile_requested = True
            self._condition.notify_all()

            while self._passes < target:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    # Timed out waiting for the pass, so we have no verdict.
                    return Recovery(session=None, session_confirmed=False)
                self._condition.wait(remaining)

            current = self._session
            if current is not observed:
                return Recovery(session=current, session_confirmed=False)
            return Recovery(
                session=None, session_confirmed=self._last_pass_confirmed_session
            )

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
        except RefreshTooSoonError:
            # The session is untouched and still good. Keeping it is the whole
            # point: reacting to this by logging in again would turn the
            # server's throttle into the re-login stampede it exists to prevent.
            logger.warning(
                "Flashlight refused to refresh our session as too recent. "
                "Keeping it and trying again later."
            )
            self._postpone(TOO_SOON_REFRESH_DELAY_SECONDS)
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
            self._finish_pass(confirmed_session=False)

    def _postpone(self, delay: float) -> None:
        """
        Nothing changed and nothing is wrong - come back later

        **Never earlier than what was already scheduled.** The session we are
        holding is good until its own refresh point, and a too-soon refusal says
        nothing about that; moving the next attempt *forward* to `delay` would
        walk into the same refusal again, and again, for as long as the server's
        minimum interval has left to run.

        Requests are held off for `delay` as well. The server has just told us it
        will not touch this session, so asking again per 401 would only reproduce
        the answer - and one of the two things that produce a 429 is the refresh
        endpoint's own rate limit.
        """
        with self._condition:
            retry_at = self._monotonic() + delay
            self._next_action_at = max(retry_at, self._next_action_at)
            self._retry_not_before = retry_at
            self._finish_pass(confirmed_session=True)

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
            self._finish_pass(confirmed_session=False)

    def _finish_pass(self, *, confirmed_session: bool) -> None:
        """Publish the outcome of a reconcile pass. Caller holds the condition."""
        # Cleared here, at the *end* of the pass. A request that reported a 401 or
        # a refresh hint while this pass was in flight has already been served by
        # it - the pass read the very session it is reporting about - so leaving
        # the flag set would make the auth thread immediately reconcile again.
        # Right after a successful refresh that second pass is a refresh the
        # server refuses as too soon, and every bearer response carries
        # `X-Auth-Refresh` from exactly the moment our own timer fires, so a
        # lobby fan-out sets the flag every single time.
        self._reconcile_requested = False
        self._last_pass_confirmed_session = confirmed_session
        self._passes += 1
        self._condition.notify_all()
