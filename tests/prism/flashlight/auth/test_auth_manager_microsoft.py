import pytest

from prism.flashlight.auth.errors import (
    AuthError,
    CredentialRejectedError,
    RefreshRateLimitedError,
    SessionExpiredError,
)
from prism.flashlight.auth.manager import INITIAL_BACKOFF_SECONDS
from prism.flashlight.auth.session import Session
from tests.prism.auth_utils import (
    TEST_UUID,
    QueuedMicrosoftLogin,
    make_auth_manager,
    make_fast_forward_auth_manager,
    make_microsoft_auth_manager,
    make_session,
    running_auth_thread,
)

OTHER_UUID = "0e7b5d9b-1c2a-4a3b-9c4d-5e6f7a8b9c0d"


def test_an_anonymous_manager_is_not_signed_in() -> None:
    manager = make_fast_forward_auth_manager()

    assert manager.tier == "test"
    assert manager.signed_in_uuid is None
    assert not manager.microsoft_signin_ended
    assert manager.wait_for_session() is None


def test_starts_on_the_microsoft_tier_when_given_one() -> None:
    session = make_session(tier="microsoft")
    manager, microsoft, anonymous, _ = make_microsoft_auth_manager(
        microsoft_results=[session]
    )

    assert manager.tier == "microsoft"
    assert manager.signed_in_uuid == TEST_UUID

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is session
    assert (microsoft.calls, anonymous.calls) == (1, 0)


def test_a_rejected_credential_falls_back_to_anonymous_in_the_same_pass() -> None:
    session = make_session(tier="anonymous")
    manager, microsoft, anonymous, _ = make_microsoft_auth_manager(
        microsoft_results=[CredentialRejectedError("401")],
        anonymous_results=[session],
    )

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is session
    assert manager.tier == "anonymous"
    assert manager.signed_in_uuid is None
    assert manager.microsoft_signin_ended
    # No backoff
    assert manager.consecutive_failures == 0
    assert manager.seconds_until_next_action() == session.refresh_in_seconds


def test_after_a_rejected_credential_it_stays_anonymous() -> None:
    manager, microsoft, anonymous, _ = make_microsoft_auth_manager(
        microsoft_results=[CredentialRejectedError("401")],
        anonymous_results=[AuthError("no network"), make_session()],
    )

    manager.reconcile()
    assert manager.microsoft_signin_ended
    assert manager.consecutive_failures == 1
    assert manager.seconds_until_next_action() == INITIAL_BACKOFF_SECONDS

    manager.reconcile()
    assert manager.wait_for_session(timeout=0) is not None
    assert (microsoft.calls, anonymous.calls) == (1, 2)


def test_a_transient_recover_failure_keeps_microsoft_and_backs_off() -> None:
    session = make_session(tier="microsoft")
    manager, microsoft, anonymous, _ = make_microsoft_auth_manager(
        microsoft_results=[AuthError("status code 503"), session],
    )

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is None
    assert manager.tier == "microsoft"
    assert not manager.microsoft_signin_ended
    assert manager.consecutive_failures == 1
    assert manager.seconds_until_next_action() == INITIAL_BACKOFF_SECONDS

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is session
    assert (microsoft.calls, anonymous.calls) == (2, 0)


def test_at_the_lifetime_cap_a_microsoft_session_recovers() -> None:
    """canRefresh=False at the 24 h cap: recover, never anonymous login"""
    capped = make_session(tier="microsoft", can_refresh=False)
    recovered = make_session(session_id="flsess_recovered", tier="microsoft")
    manager, microsoft, anonymous, refresh = make_microsoft_auth_manager(
        microsoft_results=[capped, recovered]
    )

    manager.reconcile()
    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is recovered
    assert (microsoft.calls, anonymous.calls) == (2, 0)
    assert refresh.session_ids == []


def test_a_finished_microsoft_session_recovers() -> None:
    """A refresh 401 also goes to recover, never anonymous login"""
    session = make_session(session_id="flsess_finished", tier="microsoft")
    recovered = make_session(session_id="flsess_recovered", tier="microsoft")
    manager, microsoft, anonymous, refresh = make_microsoft_auth_manager(
        microsoft_results=[session, recovered],
        refresh_results=[SessionExpiredError("401")],
    )
    manager.reconcile()

    with running_auth_thread(manager):
        assert manager.recover_from_unauthorized(session, timeout=5) is recovered

    assert refresh.session_ids == ["flsess_finished"]
    assert (microsoft.calls, anonymous.calls) == (2, 0)


def test_adopt_swaps_the_method_and_the_session() -> None:
    adopted = make_session(
        session_id="flsess_adopted", tier="microsoft", can_refresh=False
    )
    recovered = make_session(session_id="flsess_recovered", tier="microsoft")
    manager, anonymous, _ = make_auth_manager(login_results=[make_session()])
    microsoft = QueuedMicrosoftLogin([recovered], uuid=OTHER_UUID)
    manager.reconcile()

    manager.adopt(adopted, microsoft)

    assert manager.wait_for_session(timeout=0) is adopted
    assert manager.tier == "microsoft"
    assert manager.signed_in_uuid == OTHER_UUID
    assert manager.seconds_until_next_action() == adopted.refresh_in_seconds

    # The next login is a recover
    manager.reconcile()
    assert manager.wait_for_session(timeout=0) is recovered
    assert (microsoft.calls, anonymous.calls) == (1, 1)


def test_adopt_clears_microsoft_signin_ended() -> None:
    manager, microsoft, _, _ = make_microsoft_auth_manager(
        microsoft_results=[CredentialRejectedError("401")],
        anonymous_results=[make_session()],
    )
    manager.reconcile()
    assert manager.microsoft_signin_ended

    manager.adopt(make_session(tier="microsoft"), microsoft)

    assert not manager.microsoft_signin_ended
    assert manager.tier == "microsoft"


def test_dismiss_signin_ended_clears_the_flag_and_keeps_the_session() -> None:
    session = make_session()
    manager, _, _, _ = make_microsoft_auth_manager(
        microsoft_results=[CredentialRejectedError("401")],
        anonymous_results=[session],
    )
    manager.reconcile()
    assert manager.microsoft_signin_ended

    manager.dismiss_signin_ended()

    assert not manager.microsoft_signin_ended
    assert manager.tier == "anonymous"
    assert manager.wait_for_session(timeout=0) is session


def test_adopt_clears_a_failure_backoff() -> None:
    manager, anonymous, _ = make_auth_manager(login_results=[AuthError("down")])
    manager.reconcile()
    assert manager.consecutive_failures == 1

    manager.adopt(make_session(tier="microsoft"), QueuedMicrosoftLogin())

    assert manager.consecutive_failures == 0
    assert manager.last_error is None


def test_adopt_wins_over_a_pass_in_flight() -> None:
    """
    The pass read the old method, so its result must not replace the adopted one

    Otherwise a refresh of the anonymous session landing just after sign-in
    would keep the overlay anonymous until the 24 h cap.
    """
    adopted = make_session(session_id="flsess_adopted", tier="microsoft")
    manager, anonymous, _ = make_auth_manager()
    microsoft = QueuedMicrosoftLogin()

    def adopt_mid_login() -> Session:
        manager.adopt(adopted, microsoft)
        return make_session(session_id="flsess_stale_anonymous")

    anonymous.results.append(adopt_mid_login)

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is adopted
    assert manager.tier == "microsoft"
    assert manager.seconds_until_next_action() == adopted.refresh_in_seconds


def test_adopt_wins_over_a_failing_pass_in_flight() -> None:
    adopted = make_session(session_id="flsess_adopted", tier="microsoft")
    manager, anonymous, _ = make_auth_manager()

    def adopt_mid_login() -> Session:
        manager.adopt(adopted, QueuedMicrosoftLogin())
        raise AuthError("no network")

    anonymous.results.append(adopt_mid_login)

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is adopted
    assert manager.consecutive_failures == 0
    assert manager.seconds_until_next_action() == adopted.refresh_in_seconds


def test_adopt_wins_over_a_rate_limited_refresh_in_flight() -> None:
    adopted = make_session(session_id="flsess_adopted", tier="microsoft")
    manager, _, refresh = make_auth_manager(login_results=[make_session()])
    manager.reconcile()

    def adopt_mid_refresh(session_id: str) -> Session:
        manager.adopt(adopted, QueuedMicrosoftLogin())
        raise RefreshRateLimitedError("slow down")

    refresh.results.append(adopt_mid_refresh)

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is adopted
    assert manager.seconds_until_next_action() == adopted.refresh_in_seconds


def test_sign_out_to_anonymous() -> None:
    microsoft_session = make_session(tier="microsoft")
    anonymous_session = make_session(session_id="flsess_anonymous")
    manager, microsoft, anonymous, _ = make_microsoft_auth_manager(
        microsoft_results=[microsoft_session], anonymous_results=[anonymous_session]
    )
    manager.reconcile()

    manager.sign_out_to_anonymous()

    assert manager.wait_for_session(timeout=0) is None
    assert manager.tier == "anonymous"
    assert manager.signed_in_uuid is None
    assert not manager.microsoft_signin_ended
    assert manager.seconds_until_next_action() == 0.0

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is anonymous_session
    assert (microsoft.calls, anonymous.calls) == (1, 1)


def test_sign_out_wins_over_a_pass_in_flight() -> None:
    manager, microsoft, anonymous, _ = make_microsoft_auth_manager()

    def sign_out_mid_recover() -> Session:
        manager.sign_out_to_anonymous()
        return make_session(session_id="flsess_stale_microsoft", tier="microsoft")

    microsoft.results.append(sign_out_mid_recover)

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is None
    assert manager.tier == "anonymous"
    # The sign-out's pass is still owed
    assert manager.seconds_until_next_action() == 0.0


def test_a_stale_pass_does_not_log_in_with_the_new_method() -> None:
    """Recovering would rotate the new credential and waste a session"""
    adopted = make_session(session_id="flsess_adopted", tier="microsoft")
    manager, anonymous, refresh = make_auth_manager(
        login_results=[make_session(), make_session(session_id="flsess_stale")]
    )
    manager.reconcile()
    # No results: a call fails the test
    microsoft = QueuedMicrosoftLogin()

    def adopt_mid_refresh(session_id: str) -> Session:
        manager.adopt(adopted, microsoft)
        raise SessionExpiredError("401")

    refresh.results.append(adopt_mid_refresh)

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is adopted
    assert (microsoft.calls, anonymous.calls) == (0, 2)


def test_a_stale_rejection_does_not_end_a_sign_in_with_the_same_method() -> None:
    """The sign-in thread may adopt with the same method object"""
    adopted = make_session(session_id="flsess_adopted", tier="microsoft")
    manager, microsoft, anonymous, _ = make_microsoft_auth_manager()

    def adopt_mid_recover() -> Session:
        manager.adopt(adopted, microsoft)
        raise CredentialRejectedError("401")

    microsoft.results.append(adopt_mid_recover)

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is adopted
    assert manager.tier == "microsoft"
    assert not manager.microsoft_signin_ended
    assert anonymous.calls == 0


def test_a_stale_pass_does_not_swallow_a_request_for_a_pass() -> None:
    """A 401 on the adopted session, reported mid-pass, still gets its own pass"""
    adopted = make_session(session_id="flsess_adopted", tier="microsoft")
    manager, anonymous, _ = make_auth_manager()

    def adopt_and_report_mid_login() -> Session:
        manager.adopt(adopted, QueuedMicrosoftLogin())
        manager.note_refresh_hint(adopted)
        return make_session(session_id="flsess_stale")

    anonymous.results.append(adopt_and_report_mid_login)

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is adopted
    assert manager.seconds_until_next_action() == 0.0


def test_sign_out_clears_the_failure_state() -> None:
    manager, _, _, _ = make_microsoft_auth_manager(
        microsoft_results=[AuthError("status code 503")]
    )
    manager.reconcile()
    assert manager.consecutive_failures == 1

    manager.sign_out_to_anonymous()

    assert manager.consecutive_failures == 0
    assert manager.last_error is None


@pytest.mark.parametrize("rejected", (True, False))
def test_a_rejected_credential_after_a_swap_does_not_downgrade(
    rejected: bool,
) -> None:
    """A stale method's rejection must not end the sign-in that replaced it"""
    adopted = make_session(session_id="flsess_adopted", tier="microsoft")
    # No anonymous results: falling back would fail the test
    manager, old, anonymous, _ = make_microsoft_auth_manager()
    new = QueuedMicrosoftLogin(uuid=OTHER_UUID)

    def adopt_mid_recover() -> Session:
        manager.adopt(adopted, new)
        if rejected:
            raise CredentialRejectedError("401")
        raise AuthError("no network")

    old.results.append(adopt_mid_recover)

    manager.reconcile()

    assert manager.wait_for_session(timeout=0) is adopted
    assert manager.signed_in_uuid == OTHER_UUID
    assert not manager.microsoft_signin_ended
