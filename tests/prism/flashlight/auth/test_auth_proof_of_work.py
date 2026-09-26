import hashlib
import itertools
from pathlib import Path

import pytest

from prism.flashlight.auth import native_pow, proof_of_work
from prism.flashlight.auth.errors import AuthError
from prism.flashlight.auth.proof_of_work import (
    ALGORITHM_SHA256_LEADING_ZEROS,
    MAX_DIFFICULTY,
    NATIVE_PREFERENCE,
    PYTHON_SOLVER,
    Challenge,
    Solver,
    default_solver,
    difficulty_target,
    get_solver,
    leading_zero_bits,
    parse_challenge_response,
    pick_default_solver,
    self_test,
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


def make_challenge(*, difficulty: int = 0, algorithm: str | None = None) -> Challenge:
    return Challenge(
        challenge="a-challenge",
        algorithm=ALGORITHM_SHA256_LEADING_ZEROS if algorithm is None else algorithm,
        difficulty=difficulty,
    )


def test_parse_challenge_response() -> None:
    assert parse_challenge_response(VALID_RESPONSE) == Challenge(
        challenge=VALID_RESPONSE["challenge"],  # type: ignore[arg-type]
        algorithm=ALGORITHM_SHA256_LEADING_ZEROS,
        difficulty=0,
    )


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
    )
    solution = solve_challenge(challenge, solver=get_solver(solver_name))

    # A non-empty solution is required even at difficulty 0
    assert solution

    digest = hashlib.sha256(f"{challenge.challenge}:{solution}".encode()).digest()
    assert leading_zero_bits(digest) >= difficulty


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

    assert solve_challenge(challenge, solver=PYTHON_SOLVER) == reference()


def test_solve_challenge_at_difficulty_zero_is_one_hash() -> None:
    assert solve_challenge(make_challenge(difficulty=0), solver=PYTHON_SOLVER) == (
        "0000"
    )
    assert solve_challenge(
        make_challenge(difficulty=0), solver=get_solver("portable")
    ) == ("000000000000")


def test_solve_challenge_rejects_unknown_algorithm() -> None:
    """A scheme we don't implement must be an error, never a guess"""
    with pytest.raises(AuthError, match="Unsupported proof-of-work algorithm"):
        solve_challenge(make_challenge(algorithm="sha256-leading-zeros-v2"))


def test_solve_challenge_refuses_difficulty_above_the_ceiling() -> None:
    """A server bug must not wedge the overlay in a hash loop"""
    with pytest.raises(AuthError, match="Refusing proof-of-work difficulty"):
        solve_challenge(make_challenge(difficulty=MAX_DIFFICULTY + 1))


def test_solve_challenge_logs_noteworthy_difficulties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(proof_of_work, "NOTEWORTHY_DIFFICULTY", 4)
    assert solve_challenge(make_challenge(difficulty=4))


def test_solve_challenge_wraps_native_errors() -> None:
    def fail(prefix: bytes, difficulty: int) -> str:
        raise native_pow.NativePowError("broken")

    with pytest.raises(AuthError, match="'broken-solver' failed"):
        solve_challenge(make_challenge(), solver=Solver("broken-solver", fail))


def test_get_solver_python() -> None:
    assert get_solver("python") is PYTHON_SOLVER


def test_get_solver_portable() -> None:
    solver = get_solver("portable")
    assert solver.name == "portable"
    assert solve_challenge(make_challenge(difficulty=8), solver=solver)


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
    def wrong(prefix: bytes, difficulty: int) -> str:
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
