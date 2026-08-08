import hashlib

import pytest

from prism.flashlight.auth import proof_of_work
from prism.flashlight.auth.errors import AuthError
from prism.flashlight.auth.proof_of_work import (
    ALGORITHM_SHA256_LEADING_ZEROS,
    MAX_DIFFICULTY,
    Challenge,
    leading_zero_bits,
    parse_challenge_response,
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


@pytest.mark.parametrize("difficulty", (0, 1, 4, 8))
def test_solve_challenge(difficulty: int) -> None:
    challenge = make_challenge(difficulty=difficulty)
    solution = solve_challenge(challenge)

    # A non-empty solution is required even at difficulty 0
    assert solution

    digest = hashlib.sha256(f"{challenge.challenge}:{solution}".encode()).digest()
    assert leading_zero_bits(digest) >= difficulty


def test_solve_challenge_at_difficulty_zero_is_one_hash() -> None:
    assert solve_challenge(make_challenge(difficulty=0)) == "0"


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
