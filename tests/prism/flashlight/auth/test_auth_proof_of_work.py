import hashlib
import itertools
import logging
from pathlib import Path

import pytest

from prism.flashlight.auth import native_pow, proof_of_work
from prism.flashlight.auth.errors import AuthError
from prism.flashlight.auth.proof_of_work import (
    ALGORITHM_SHA256_LEADING_ZEROS,
    DEFAULT_CHALLENGE_TTL_SECONDS,
    NATIVE_PREFERENCE,
    PYTHON_SOLVER,
    Challenge,
    Deadline,
    ProofOfWorkTimeoutError,
    Solver,
    SolveReport,
    SolveTimeout,
    default_solver,
    difficulty_target,
    get_solver,
    leading_zero_bits,
    parse_challenge_response,
    pick_default_solver,
    self_test,
    solve_budget,
    solve_challenge,
)

# A real response from POST /v1/auth/anonymous/challenge
VALID_RESPONSE = {
    "challenge": (
        "eyJub25jZSI6IkFBQUFBQUFBQUFBQUFBQUFBQSIsInVzZXJJZCI6InByaXNtIn0"
        ".c3VyZWx5LW5vdC1hLXJlYWwtc2lnbmF0dXJlLWJ1dC1sb25nLWVub3VnaA"
    ),
    "algorithm": ALGORITHM_SHA256_LEADING_ZEROS,
    "difficulty": 0,
    "expiresInSeconds": 60,
}


def make_challenge(
    *,
    difficulty: int = 0,
    algorithm: str | None = None,
    expires_in_seconds: float = 60,
) -> Challenge:
    return Challenge(
        challenge="a-challenge",
        algorithm=ALGORITHM_SHA256_LEADING_ZEROS if algorithm is None else algorithm,
        difficulty=difficulty,
        expires_in_seconds=expires_in_seconds,
    )


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class ExpiresAfter:
    """A deadline that expires on check number `checks + 1`"""

    def __init__(self, checks: int) -> None:
        self.checks_left = checks

    def expired(self) -> bool:
        self.checks_left -= 1
        return self.checks_left < 0


NEVER = ExpiresAfter(1 << 62)


def test_parse_challenge_response() -> None:
    assert parse_challenge_response(VALID_RESPONSE) == Challenge(
        challenge=VALID_RESPONSE["challenge"],  # type: ignore[arg-type]
        algorithm=ALGORITHM_SHA256_LEADING_ZEROS,
        difficulty=0,
        expires_in_seconds=60,
    )


@pytest.mark.parametrize("difficulty", (27, 33, 256))
def test_parse_challenge_response_has_no_difficulty_cap(difficulty: int) -> None:
    challenge = parse_challenge_response({**VALID_RESPONSE, "difficulty": difficulty})
    assert challenge.difficulty == difficulty


@pytest.mark.parametrize(
    "expires_in_seconds, expected",
    (
        (30, 30),
        (2.5, 2.5),
        (1000, 1000),
        # Bad values fall back: the field only sizes our time budget
        (None, DEFAULT_CHALLENGE_TTL_SECONDS),
        ("60", DEFAULT_CHALLENGE_TTL_SECONDS),
        (True, DEFAULT_CHALLENGE_TTL_SECONDS),
        (0, DEFAULT_CHALLENGE_TTL_SECONDS),
        (-5, DEFAULT_CHALLENGE_TTL_SECONDS),
        (float("nan"), DEFAULT_CHALLENGE_TTL_SECONDS),
        (float("inf"), DEFAULT_CHALLENGE_TTL_SECONDS),
    ),
)
def test_parse_challenge_response_expiry(
    expires_in_seconds: object, expected: float
) -> None:
    challenge = parse_challenge_response(
        {**VALID_RESPONSE, "expiresInSeconds": expires_in_seconds}
    )
    assert challenge.expires_in_seconds == expected


def test_parse_challenge_response_missing_expiry() -> None:
    response = {k: v for k, v in VALID_RESPONSE.items() if k != "expiresInSeconds"}
    challenge = parse_challenge_response(response)
    assert challenge.expires_in_seconds == DEFAULT_CHALLENGE_TTL_SECONDS


@pytest.mark.parametrize(
    "expires_in_seconds, budget",
    (
        (60, 55),
        # A bad server value can't hold the auth thread for long
        (1000, 115),
        # A short TTL still gets a fair try
        (3, 10),
        (14, 10),
    ),
)
def test_solve_budget(expires_in_seconds: float, budget: float) -> None:
    assert solve_budget(make_challenge(expires_in_seconds=expires_in_seconds)) == (
        budget
    )


def test_deadline_monotonic() -> None:
    monotonic, wall = FakeClock(), FakeClock()
    deadline = Deadline(10, monotonic=monotonic, wall=wall)
    assert not deadline.expired()
    monotonic.now += 9.9
    wall.now += 9.9
    assert not deadline.expired()
    monotonic.now += 0.1
    assert deadline.expired()


def test_deadline_wall_clock_covers_suspend() -> None:
    """Linux's monotonic clock stops in suspend, the server's TTL does not"""
    monotonic, wall = FakeClock(), FakeClock()
    deadline = Deadline(10, monotonic=monotonic, wall=wall)
    wall.now += 3600
    assert deadline.expired()


def test_deadline_monotonic_covers_wall_clock_going_back() -> None:
    monotonic, wall = FakeClock(), FakeClock()
    deadline = Deadline(10, monotonic=monotonic, wall=wall)
    wall.now -= 3600
    monotonic.now += 10
    assert deadline.expired()


def test_parse_challenge_response_keeps_unknown_algorithms() -> None:
    """Refusing an algorithm is solve_challenge's job, not the parser's"""
    challenge = parse_challenge_response({**VALID_RESPONSE, "algorithm": "sha512-v2"})
    assert challenge.algorithm == "sha512-v2"


@pytest.mark.parametrize(
    "response_json",
    (
        # Not a dict
        None,
        [],
        "challenge",
        # Bad challenge
        {**VALID_RESPONSE, "challenge": ""},
        {**VALID_RESPONSE, "challenge": None},
        {**VALID_RESPONSE, "challenge": 123},
        # Bad algorithm
        {**VALID_RESPONSE, "algorithm": ""},
        {**VALID_RESPONSE, "algorithm": None},
        {**VALID_RESPONSE, "algorithm": 1},
        # Bad difficulty
        {**VALID_RESPONSE, "difficulty": None},
        {**VALID_RESPONSE, "difficulty": "0"},
        {**VALID_RESPONSE, "difficulty": 1.5},
        {**VALID_RESPONSE, "difficulty": True},
        {**VALID_RESPONSE, "difficulty": -1},
        # More zero bits than a digest has
        {**VALID_RESPONSE, "difficulty": 257},
    ),
)
def test_parse_challenge_response_invalid(response_json: object) -> None:
    with pytest.raises(AuthError):
        parse_challenge_response(response_json)


@pytest.mark.parametrize(
    "digest, bits",
    (
        (bytes([0xFF]) + bytes(31), 0),
        (bytes([0x80]) + bytes(31), 0),
        (bytes([0x7F]) + bytes(31), 1),
        (bytes([0x01]) + bytes(31), 7),
        (bytes([0x00, 0xFF]) + bytes(30), 8),
        (bytes([0x00, 0x01]) + bytes(30), 15),
        (bytes(32), 256),
    ),
)
def test_leading_zero_bits(digest: bytes, bits: int) -> None:
    assert leading_zero_bits(digest) == bits


@pytest.mark.parametrize("difficulty", range(0, 27))
def test_difficulty_target(difficulty: int) -> None:
    """`digest < target` must agree with counting leading zero bits"""
    target = difficulty_target(difficulty)

    # The digests either side of the boundary, and the extremes
    boundary = 1 << (256 - difficulty)
    digests = [bytes(32), b"\xff" * 32]
    digests += [
        n.to_bytes(32, "big") for n in (boundary - 1, boundary) if n < (1 << 256)
    ]

    for digest in digests:
        assert (digest < target) == (leading_zero_bits(digest) >= difficulty)


@pytest.mark.parametrize("solver_name", ("python", "native"))
@pytest.mark.parametrize("difficulty", (0, 1, 4, 8, 12))
@pytest.mark.parametrize("challenge_length", (1, 11, 54, 63, 64, 65, 341))
def test_solve_challenge(
    solver_name: str, difficulty: int, challenge_length: int
) -> None:
    challenge = Challenge(
        challenge="c" * challenge_length,
        algorithm=ALGORITHM_SHA256_LEADING_ZEROS,
        difficulty=difficulty,
        expires_in_seconds=60,
    )
    solver = get_solver(solver_name)
    report = solve_challenge(challenge, solver=solver)
    solution = report.solution

    # A non-empty solution is required even at difficulty 0
    assert solution

    digest = hashlib.sha256(f"{challenge.challenge}:{solution}".encode()).digest()
    assert leading_zero_bits(digest) >= difficulty

    assert report.difficulty == difficulty
    assert report.solver == solver.name
    # Every solver counts up from 0, so the solution is the attempts made
    assert report.hashes == int(solution) + 1
    assert report.elapsed_seconds >= 0
    assert report.cpu_seconds >= 0


@pytest.mark.parametrize("difficulty", (0, 6, 10))
def test_solve_challenge_returns_first_candidate(difficulty: int) -> None:
    """The solver must not skip candidates: compare with a plain loop"""
    challenge = make_challenge(difficulty=difficulty)

    def reference() -> str:
        for high in itertools.count():
            for low in range(1000):
                candidate = f"{high}{low:03d}"
                digest = hashlib.sha256(
                    f"{challenge.challenge}:{candidate}".encode()
                ).digest()
                if leading_zero_bits(digest) >= difficulty:
                    return candidate
        assert False  # pragma: nocover

    assert solve_challenge(challenge, solver=PYTHON_SOLVER).solution == reference()


def test_solve_challenge_at_difficulty_zero_is_one_hash() -> None:
    report = solve_challenge(make_challenge(difficulty=0), solver=PYTHON_SOLVER)
    assert (report.solution, report.hashes) == ("0000", 1)
    report = solve_challenge(
        make_challenge(difficulty=0), solver=get_solver("portable")
    )
    assert (report.solution, report.hashes) == ("000000000000", 1)


def test_solve_challenge_rejects_unknown_algorithm() -> None:
    """A scheme we don't implement must be an error, never a guess"""
    with pytest.raises(AuthError, match="Unsupported proof-of-work algorithm"):
        solve_challenge(make_challenge(algorithm="sha256-leading-zeros-v2"))


def test_solve_challenge_has_no_difficulty_cap() -> None:
    """The time budget is the limit, so faster hardware can do more"""
    seen: list[int] = []

    def solve(prefix: bytes, difficulty: int, deadline: object) -> str:
        seen.append(difficulty)
        return "41"

    report = solve_challenge(make_challenge(difficulty=40), solver=Solver("s", solve))
    assert seen == [40]
    assert report.hashes == 42


def test_solve_challenge_passes_its_deadline_on() -> None:
    seen: list[object] = []

    def solve(prefix: bytes, difficulty: int, deadline: object) -> str:
        seen.append(deadline)
        return "0"

    solve_challenge(make_challenge(), solver=Solver("s", solve), deadline=NEVER)
    assert seen == [NEVER]


def test_solve_challenge_makes_a_deadline_from_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    budgets: list[float] = []

    class RecordingDeadline:
        def __init__(self, seconds: float) -> None:
            budgets.append(seconds)

        def expired(self) -> bool:  # pragma: nocover
            return False

    monkeypatch.setattr(proof_of_work, "Deadline", RecordingDeadline)
    solve_challenge(make_challenge(expires_in_seconds=30), solver=PYTHON_SOLVER)
    assert budgets == [25]


@pytest.mark.parametrize("solver_name", ("python", "portable", "native"))
def test_solve_challenge_times_out(solver_name: str) -> None:
    # Unsolvable in any time we would wait for
    challenge = make_challenge(difficulty=64)
    with pytest.raises(ProofOfWorkTimeoutError) as info:
        solve_challenge(
            challenge, solver=get_solver(solver_name), deadline=ExpiresAfter(2)
        )

    report = info.value.report
    assert report.solution is None
    assert report.difficulty == 64
    assert report.solver == get_solver(solver_name).name
    # Two batches ran before the third check stopped it
    batch = (
        proof_of_work.PYTHON_BATCH_HASHES
        if solver_name == "python"
        else native_pow.CHUNK_SIZE
    )
    assert report.hashes == 2 * batch
    # An AuthError, so the auth manager backs off and tries again
    assert isinstance(info.value, AuthError)


def test_solve_challenge_checks_the_deadline_before_any_work() -> None:
    with pytest.raises(ProofOfWorkTimeoutError) as info:
        solve_challenge(
            make_challenge(difficulty=64),
            solver=PYTHON_SOLVER,
            deadline=ExpiresAfter(0),
        )
    assert info.value.report.hashes == 0


@pytest.mark.parametrize(
    "cpu_seconds, slow",
    ((0.0, False), (4.9, False), (5.0, True), (60.0, True)),
)
def test_solve_report_slow_is_cpu_time(cpu_seconds: float, slow: bool) -> None:
    """Wall time is not used: a suspend mid-solve is not slow hardware"""
    report = SolveReport(
        solution=None,
        difficulty=20,
        solver="python",
        hashes=0,
        elapsed_seconds=3600.0,
        cpu_seconds=cpu_seconds,
    )
    assert report.slow is slow


def test_solve_challenge_logs_start_and_end(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    result = solve_challenge(make_challenge(difficulty=4), solver=PYTHON_SOLVER)
    assert "Solving proof-of-work at difficulty 4 with solver 'python'" in caplog.text
    assert f"Solved proof-of-work: {result}" in caplog.text
    assert "Slow" not in caplog.text


def test_solve_challenge_logs_timeouts(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    with pytest.raises(ProofOfWorkTimeoutError) as info:
        solve_challenge(
            make_challenge(difficulty=64),
            solver=PYTHON_SOLVER,
            deadline=ExpiresAfter(0),
        )
    assert "Solving proof-of-work at difficulty 64" in caplog.text
    assert f"Proof-of-work timed out: {info.value.report}" in caplog.text


def test_solve_challenge_logs_slow_solves(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(proof_of_work, "SLOW_SOLVE_CPU_SECONDS", 0.0)
    assert solve_challenge(make_challenge(difficulty=0)).solution
    assert "Slow" in caplog.text


def test_solve_challenge_wraps_native_errors() -> None:
    def fail(prefix: bytes, difficulty: int, deadline: object) -> str:
        raise native_pow.NativePowError("broken")

    with pytest.raises(AuthError, match="'broken-solver' failed"):
        solve_challenge(make_challenge(), solver=Solver("broken-solver", fail))


def test_solver_timeout_without_solve_challenge() -> None:
    with pytest.raises(SolveTimeout) as info:
        PYTHON_SOLVER.solve(b"x", 64, ExpiresAfter(1))
    assert info.value.hashes == proof_of_work.PYTHON_BATCH_HASHES


def test_get_solver_python() -> None:
    assert get_solver("python") is PYTHON_SOLVER


def test_get_solver_portable() -> None:
    solver = get_solver("portable")
    assert solver.name == "portable"
    assert solve_challenge(make_challenge(difficulty=8), solver=solver).solution


def test_get_solver_native_picks_the_best_supported() -> None:
    library = native_pow.NativeLibrary(native_pow.LIBRARY_PATH)
    best = next(name for name in NATIVE_PREFERENCE if library.supported(name))
    assert get_solver("native").name == best


def test_get_solver_unknown_name() -> None:
    with pytest.raises(AuthError, match="Unknown proof-of-work solver"):
        get_solver("sha-3000")


@pytest.mark.parametrize("name", ("native", "portable"))
def test_get_solver_does_not_fall_back(name: str, tmp_path: Path) -> None:
    with pytest.raises(AuthError, match="Could not load"):
        get_solver(name, library_path=tmp_path / "missing")


def test_get_solver_refuses_unsupported_implementation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(native_pow.NativeLibrary, "supported", lambda _, __: False)
    with pytest.raises(AuthError, match="not supported"):
        get_solver("portable")
    with pytest.raises(AuthError, match="No native"):
        get_solver("native")


def test_pick_default_solver_prefers_native() -> None:
    assert pick_default_solver().name == get_solver("native").name


def test_pick_default_solver_falls_back_to_python(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert pick_default_solver(library_path=tmp_path / "missing") is PYTHON_SOLVER
    assert "falling back" in caplog.text


def test_default_solver_is_native() -> None:
    """With the library built, a real login must not use the Python solver"""
    assert default_solver().name == get_solver("native").name


@pytest.mark.parametrize("name", ("python", "portable", "native"))
def test_self_test(name: str) -> None:
    solver = self_test(name, difficulties=(0, 1, 8))
    assert solver.name == get_solver(name).name


def test_self_test_catches_wrong_solutions(monkeypatch: pytest.MonkeyPatch) -> None:
    def wrong(prefix: bytes, difficulty: int, deadline: object) -> str:
        """Return a candidate that does *not* meet the difficulty"""
        for counter in itertools.count():  # pragma: no branch
            digest = hashlib.sha256(prefix + str(counter).encode()).digest()
            if leading_zero_bits(digest) < difficulty:
                return str(counter)
        assert False  # pragma: nocover

    monkeypatch.setattr(
        proof_of_work, "get_solver", lambda _: Solver(name="wrong", solve=wrong)
    )
    with pytest.raises(AuthError, match="wrong"):
        self_test("wrong", difficulties=(8,))


def test_self_test_native_catches_a_python_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(proof_of_work, "default_solver", lambda: PYTHON_SOLVER)
    with pytest.raises(AuthError, match="default"):
        self_test("native", difficulties=(0,))
