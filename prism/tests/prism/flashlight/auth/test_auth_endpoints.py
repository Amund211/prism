import json

import pytest

from prism.flashlight.auth.endpoints import anonymous_login_body
from prism.flashlight.auth.errors import AuthError
from tests.prism.auth_utils import make_solve_report


def test_anonymous_login_body() -> None:
    report = make_solve_report(solver="sha-ni")
    body = anonymous_login_body(user_id="user", challenge="a-challenge", report=report)
    assert body == {
        "userId": "user",
        "challenge": "a-challenge",
        "solution": report.solution,
        "solver": {
            "name": "sha-ni",
            "version": report.solver_version,
            "hashes": report.hashes,
            "elapsedSeconds": report.elapsed_seconds,
            "cpuSeconds": report.cpu_seconds,
        },
    }
    json.dumps(body)


def test_anonymous_login_body_reports_the_python_fallback() -> None:
    body = anonymous_login_body(
        user_id="user", challenge="c", report=make_solve_report(solver="python")
    )
    assert body["solver"]["name"] == "python"


def test_anonymous_login_body_needs_a_solution() -> None:
    with pytest.raises(AuthError, match="timed out"):
        anonymous_login_body(
            user_id="user", challenge="c", report=make_solve_report(solution=None)
        )
