import time

import pytest

from prism.flashlight.auth.errors import (
    AuthError,
    RefreshRateLimitedError,
    SessionExpiredError,
)
from prism.flashlight.auth.manager import (
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
    RATE_LIMITED_REFRESH_DELAY_SECONDS,
)
from tests.prism.auth_utils import (
    make_auth_manager,
    make_real_clock_auth_manager,
    make_session,
    running_auth_thread,
)


def test_starts_with_no_session_and_wants_to_act_now() -> None:
    manager, login, refresh = make_auth_manager()

    assert manager.wait_for_session(timeout=0) is None
    assert manager.seconds_until_next_action() == 0.0
    assert manager.consecutive_failures == 0
    assert manager.last_error is None
    assert login.calls == 0


def test_reconcile_logs_in_when_there_is_no_session() -> None:
    session = make_session()
    manager, login, refresh = make_auth_manager(login_results=[session])

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is session
    assert login.calls == 1
    assert refresh.session_ids == []
    # Next action is the proactive refresh the server asked for
    assert manager.seconds_until_next_action() == session.refresh_in_seconds


def test_reconcile_refreshes_the_session_it_holds() -> None:
    session = make_session(session_id="flsess_first")
    refreshed = make_session(session_id="flsess_first", refresh_in_seconds=6600.0)
    manager, login, refresh = make_auth_manager(
        login_results=[session], refresh_results=[refreshed]
    )

    manager.reconcile()
    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is refreshed
    assert refresh.session_ids == ["flsess_first"]
    # No second login - the bearer was enough to pay for the identity again
    assert login.calls == 1


def test_reconcile_logs_in_again_when_the_session_is_finished() -> None:
    session = make_session(session_id="flsess_dead")
    new_session = make_session(session_id="flsess_new")
    manager, login, refresh = make_auth_manager(
        login_results=[session, new_session],
        refresh_results=[SessionExpiredError("finished")],
    )

    manager.reconcile()
    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is new_session
    assert login.calls == 2


def test_reconcile_skips_a_refresh_that_would_be_pointless() -> None:
    """canRefresh=False means the server already told us not to bother"""
    session = make_session(can_refresh=False)
    new_session = make_session(session_id="flsess_new")
    manager, login, refresh = make_auth_manager(login_results=[session, new_session])

    manager.reconcile()
    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is new_session
    assert login.calls == 2
    assert refresh.session_ids == []


def test_reconcile_keeps_the_session_when_a_refresh_is_rate_limited() -> None:
    """A 429 leaves the session untouched, so keep it rather than log in again"""
    session = make_session(refresh_in_seconds=60.0)
    manager, login, refresh = make_auth_manager(
        login_results=[session], refresh_results=[RefreshRateLimitedError("slow down")]
    )

    manager.reconcile()
    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is session
    assert login.calls == 1
    assert manager.consecutive_failures == 0
    assert manager.last_error is None
    assert manager.seconds_until_next_action() == RATE_LIMITED_REFRESH_DELAY_SECONDS


def test_a_rate_limited_refresh_never_schedules_earlier_than_wanted() -> None:
    """
    Otherwise one 429 becomes a loop of them

    The session we hold is good until its own refresh point and the 429 says
    nothing about it, so moving the next attempt *forward* would just spend the
    endpoint's rate limit on an answer we already have.
    """
    session = make_session(refresh_in_seconds=3300.0)
    manager, login, refresh = make_auth_manager(
        login_results=[session], refresh_results=[RefreshRateLimitedError("slow down")]
    )

    manager.reconcile()
    manager.reconcile()

    assert manager.seconds_until_next_action() == 3300.0


def test_a_request_arriving_mid_pass_does_not_provoke_a_second_one() -> None:
    """
    The refresh hint fires exactly when our own timer does

    Flashlight sets X-Auth-Refresh from the same point refreshInSeconds counts
    down to, so a lobby fan-out reports the hint while the refresh it asked for is
    still in flight. Leaving that request queued would make the auth thread
    refresh again immediately - a round trip that renews what was just renewed.
    """
    session = make_session(session_id="flsess_first")
    refreshed = make_session(session_id="flsess_first")
    manager, login, refresh = make_auth_manager(
        login_results=[session], refresh_results=[refreshed]
    )
    manager.reconcile()

    # A response carrying the hint, seen while the pass below is conceptually in
    # flight: it is reported against the session that pass is already handling.
    manager.note_refresh_hint(session)
    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is refreshed
    assert manager.seconds_until_next_action() == refreshed.refresh_in_seconds


def test_reconcile_records_a_bug_as_a_failure_before_re_raising() -> None:
    """
    Otherwise every request pays the full session wait for a pass that can't come

    The auth thread sleeps off an unexpected error, so without a retry deadline
    recover_from_unauthorized would keep queueing passes and blocking on them.
    """
    session = make_session()
    manager, login, refresh = make_auth_manager(
        login_results=[session], refresh_results=[ValueError("a bug, not a 401")]
    )
    manager.reconcile()

    with pytest.raises(ValueError):
        manager.reconcile()

    assert manager.consecutive_failures == 1
    assert manager.seconds_until_next_action() == INITIAL_BACKOFF_SECONDS
    # And a request that 401s now fails fast instead of waiting for a pass
    assert manager.recover_from_unauthorized(session, timeout=5) is None


def test_reconcile_records_failures_and_backs_off() -> None:
    manager, login, refresh = make_auth_manager(
        login_results=[
            AuthError("no network"),
            AuthError("no network"),
            make_session(),
        ]
    )

    manager.reconcile()
    assert manager.wait_for_session(timeout=0) is None
    assert manager.consecutive_failures == 1
    assert manager.last_error == "no network"
    assert manager.seconds_until_next_action() == INITIAL_BACKOFF_SECONDS

    manager.reconcile()
    assert manager.consecutive_failures == 2
    assert manager.seconds_until_next_action() == INITIAL_BACKOFF_SECONDS * 2

    manager.reconcile()
    assert manager.wait_for_session(timeout=0) is not None
    assert manager.consecutive_failures == 0
    assert manager.last_error is None


def test_reconcile_caps_the_backoff() -> None:
    manager, login, refresh = make_auth_manager(login_results=[AuthError("nope")] * 20)

    for _ in range(20):
        manager.reconcile()

    assert manager.seconds_until_next_action() == MAX_BACKOFF_SECONDS


def test_reconcile_discards_a_session_it_knows_is_dead() -> None:
    """
    A token flashlight has rejected must not be handed out again

    Validating an unknown bearer costs the server an uncached transaction, so
    retrying with a token we know is dead is not a neutral act.
    """
    session = make_session()
    manager, login, refresh = make_auth_manager(
        login_results=[session, AuthError("login is down too")],
        refresh_results=[SessionExpiredError("finished")],
    )

    manager.reconcile()
    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is None
    assert manager.consecutive_failures == 1


def test_wait_for_session_gives_up_when_there_is_nothing_to_wait_for() -> None:
    """Bounded, because the denick dialog waits on the tkinter thread"""
    manager = make_real_clock_auth_manager()

    started = time.monotonic()
    assert manager.wait_for_session(timeout=0.05) is None
    assert time.monotonic() - started >= 0.05


def test_recover_from_unauthorized_adopts_a_session_someone_else_got() -> None:
    """The first 401 of a fan-out does the work - the rest just adopt the result"""
    stale = make_session(session_id="flsess_stale")
    current = make_session(session_id="flsess_current")
    manager, login, refresh = make_auth_manager(login_results=[current])

    manager.reconcile()

    assert manager.recover_from_unauthorized(stale, timeout=0) is current
    # Nothing was asked of the server
    assert login.calls == 1
    assert refresh.session_ids == []


def test_recover_from_unauthorized_has_nothing_to_offer_after_a_429() -> None:
    """
    A rate limited refresh is not the server vouching for our session

    The refresh endpoint's IP limiters answer ahead of the handler that reads the
    bearer, so a 429 says nothing about the session we sent - and a caller told
    otherwise blames its own 401 on an Urchin API key that is fine.
    """
    session = make_session()
    manager, login, refresh = make_auth_manager(
        login_results=[session], refresh_results=[RefreshRateLimitedError("slow down")]
    )
    manager.reconcile()

    with running_auth_thread(manager):
        assert manager.recover_from_unauthorized(session, timeout=5) is None


def test_recover_from_unauthorized_gives_up_while_auth_is_failing() -> None:
    """
    16 stats threads must not out-vote the auth thread's backoff

    And while auth is failing we have nothing to retry with, so nothing may be
    told that its own 401 is explained.
    """
    session = make_session()
    manager, login, refresh = make_auth_manager(
        login_results=[session],
        refresh_results=[AuthError("no network")],
    )

    manager.reconcile()
    manager.reconcile()

    assert manager.recover_from_unauthorized(session, timeout=0) is None
    # No pass was requested, so the auth thread still gets to sleep off its backoff
    assert manager.seconds_until_next_action() == INITIAL_BACKOFF_SECONDS


def test_recover_from_unauthorized_has_nothing_when_the_wait_times_out() -> None:
    session = make_session()
    manager, login, refresh = make_auth_manager(login_results=[session])

    manager.reconcile()

    # No auth thread running, so the requested pass never completes
    assert manager.recover_from_unauthorized(session, timeout=0) is None


def test_recover_from_unauthorized_waits_for_the_auth_thread() -> None:
    session = make_session(session_id="flsess_lapsed")
    renewed = make_session(session_id="flsess_lapsed", refresh_in_seconds=6600.0)
    manager, login, refresh = make_auth_manager(
        login_results=[session], refresh_results=[renewed]
    )

    manager.reconcile()
    observed = manager.wait_for_session(timeout=0)
    assert observed is session

    with running_auth_thread(manager):
        assert manager.recover_from_unauthorized(observed, timeout=5) is renewed

    assert refresh.session_ids == ["flsess_lapsed"]


def test_note_refresh_hint_asks_for_a_pass() -> None:
    session = make_session()
    manager, login, refresh = make_auth_manager(login_results=[session])

    manager.reconcile()
    assert manager.seconds_until_next_action() == session.refresh_in_seconds

    manager.note_refresh_hint(session)

    assert manager.seconds_until_next_action() == 0.0


def test_note_refresh_hint_ignores_a_stale_session() -> None:
    session = make_session(session_id="flsess_current")
    manager, login, refresh = make_auth_manager(login_results=[session])

    manager.reconcile()
    manager.note_refresh_hint(make_session(session_id="flsess_stale"))

    assert manager.seconds_until_next_action() == session.refresh_in_seconds


def test_note_refresh_hint_respects_the_backoff() -> None:
    session = make_session()
    manager, login, refresh = make_auth_manager(
        login_results=[session], refresh_results=[AuthError("no network")]
    )

    manager.reconcile()
    manager.reconcile()
    manager.note_refresh_hint(session)

    assert manager.seconds_until_next_action() == INITIAL_BACKOFF_SECONDS
