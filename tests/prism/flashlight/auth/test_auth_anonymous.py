from typing import Any

import pytest
import requests

from prism.flashlight.auth import anonymous
from prism.flashlight.auth.anonymous import AnonymousLogin
from prism.flashlight.auth.proof_of_work import (
    ALGORITHM_SHA256_LEADING_ZEROS,
    Challenge,
    ProofOfWorkTimeoutError,
    SolveReport,
)
from tests.prism.auth_utils import make_solve_report

CHALLENGE = Challenge(
    challenge="a-challenge",
    algorithm=ALGORITHM_SHA256_LEADING_ZEROS,
    difficulty=4,
    expires_in_seconds=60,
)


@pytest.fixture
def login(monkeypatch: pytest.MonkeyPatch) -> AnonymousLogin:
    monkeypatch.setattr(anonymous, "request_challenge", lambda **_: CHALLENGE)
    return AnonymousLogin(requests_session=requests.Session(), user_id="user")


def test_log_in_records_the_solve(
    login: AnonymousLogin, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = make_solve_report(solution="9")
    monkeypatch.setattr(anonymous, "solve_challenge", lambda _: report)
    calls: list[dict[str, Any]] = []
    session = object()

    def fake_login(**kwargs: Any) -> object:
        calls.append(kwargs)
        return session

    monkeypatch.setattr(anonymous, "anonymous_login", fake_login)

    assert login.last_solve is None
    assert login.log_in() is session
    assert login.last_solve is report
    assert calls[0]["challenge"] == "a-challenge"
    assert calls[0]["report"] is report
    assert calls[0]["user_id"] == "user"


def test_log_in_records_a_timed_out_solve(
    login: AnonymousLogin, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = make_solve_report(solution=None)

    def time_out(_: Challenge) -> SolveReport:
        raise ProofOfWorkTimeoutError(report)

    monkeypatch.setattr(anonymous, "solve_challenge", time_out)

    with pytest.raises(ProofOfWorkTimeoutError):
        login.log_in()
    assert login.last_solve is report
