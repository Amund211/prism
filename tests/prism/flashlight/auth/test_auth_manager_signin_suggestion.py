from prism.flashlight.auth.errors import (
    AnonymousRateLimitedError,
    AuthError,
    CredentialRejectedError,
)
from prism.flashlight.auth.manager import SIGNIN_SUGGESTION_SECONDS, AuthManager
from prism.flashlight.auth.proof_of_work import (
    SLOW_SOLVE_CPU_SECONDS,
    ProofOfWorkTimeoutError,
)
from prism.flashlight.auth.session import Session
from tests.prism.auth_utils import (
    QueuedLoginMethod,
    make_auth_manager,
    make_microsoft_auth_manager,
    make_session,
    make_solve_report,
)

SLOW = make_solve_report(cpu_seconds=SLOW_SOLVE_CPU_SECONDS)
FAST = make_solve_report(cpu_seconds=0.1)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make_manager(
    login_results: list[Session | Exception] | None = None,
) -> tuple[AuthManager, QueuedLoginMethod, Clock]:
    clock = Clock()
    manager, anonymous, _ = make_auth_manager(
        login_results=login_results or [], monotonic=clock
    )
    return manager, anonymous, clock


def test_no_suggestion_by_default() -> None:
    manager, _, _ = make_manager([make_session()])
    manager.reconcile()

    assert not manager.suggest_signin


def test_suggest_after_a_rate_limit_for_a_while() -> None:
    manager, _, clock = make_manager()

    manager.note_rate_limited()
    assert manager.suggest_signin

    clock.now = SIGNIN_SUGGESTION_SECONDS - 1
    assert manager.suggest_signin

    clock.now = SIGNIN_SUGGESTION_SECONDS
    assert not manager.suggest_signin


def test_suggest_after_a_rate_limited_anonymous_login() -> None:
    manager, _, _ = make_manager([AnonymousRateLimitedError("429")])

    manager.reconcile()

    assert manager.suggest_signin
    assert manager.consecutive_failures == 1


def test_suggest_after_a_rate_limited_fallback_to_anonymous() -> None:
    manager, _, _, _ = make_microsoft_auth_manager(
        microsoft_results=[CredentialRejectedError("401")],
        anonymous_results=[AnonymousRateLimitedError("429")],
    )

    manager.reconcile()

    assert manager.suggest_signin


def test_no_suggestion_after_another_failed_login() -> None:
    manager, _, _ = make_manager([AuthError("503")])

    manager.reconcile()

    assert not manager.suggest_signin


def test_suggest_after_a_slow_solve_for_a_while() -> None:
    manager, anonymous, clock = make_manager()

    def slow_login() -> Session:
        anonymous.last_solve = SLOW
        return make_session()

    anonymous.results = [slow_login]
    manager.reconcile()
    assert manager.suggest_signin

    clock.now = SIGNIN_SUGGESTION_SECONDS
    assert not manager.suggest_signin


def test_suggest_after_a_slow_timed_out_solve() -> None:
    manager, anonymous, _ = make_manager()

    def timed_out_login() -> Session:
        anonymous.last_solve = SLOW
        raise ProofOfWorkTimeoutError(SLOW)

    anonymous.results = [timed_out_login]
    manager.reconcile()

    assert manager.suggest_signin


def test_no_suggestion_after_a_fast_solve() -> None:
    manager, anonymous, _ = make_manager()

    def fast_login() -> Session:
        anonymous.last_solve = FAST
        return make_session()

    anonymous.results = [fast_login]
    manager.reconcile()

    assert not manager.suggest_signin


def test_an_old_slow_solve_does_not_count_again() -> None:
    manager, anonymous, _ = make_manager([AuthError("503")])
    anonymous.last_solve = SLOW

    manager.reconcile()

    assert not manager.suggest_signin


def test_dismissed_suggestion_shows_again_on_a_new_rate_limit() -> None:
    manager, _, clock = make_manager()
    manager.note_rate_limited()

    manager.dismiss_signin_suggestion()
    assert not manager.suggest_signin

    clock.now = 1
    manager.note_rate_limited()
    assert manager.suggest_signin


def test_no_suggestion_when_signed_in() -> None:
    manager, _, anonymous, _ = make_microsoft_auth_manager(
        microsoft_results=[make_session(tier="microsoft")]
    )
    manager.reconcile()

    manager.note_rate_limited()

    assert not manager.suggest_signin


def test_a_rate_limit_while_signed_in_is_not_kept_for_later() -> None:
    manager, _, _, _ = make_microsoft_auth_manager(
        microsoft_results=[make_session(tier="microsoft")]
    )
    manager.reconcile()
    manager.note_rate_limited()

    manager.sign_out_to_anonymous()

    assert not manager.suggest_signin


def test_adopt_dismisses_the_suggestion() -> None:
    manager, microsoft, _, _ = make_microsoft_auth_manager()
    manager.sign_out_to_anonymous()
    manager.note_rate_limited()
    assert manager.suggest_signin

    manager.adopt(make_session(tier="microsoft"), microsoft)
    manager.sign_out_to_anonymous()

    assert not manager.suggest_signin
