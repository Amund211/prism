import functools
import hashlib
import itertools
import logging
import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from prism.flashlight.auth import native_pow
from prism.flashlight.auth.errors import AuthError

logger = logging.getLogger(__name__)

# The only proof-of-work scheme we implement: find a solution such that
# SHA-256(challenge + ":" + solution) has at least `difficulty` leading zero
# bits.
#
# Anything else must be an error rather than a guess. That is what lets
# flashlight introduce a v2 scheme without breaking overlays that are already
# installed - they refuse the challenge, back off and keep refusing until the
# server stops handing out a scheme they don't know.
ALGORITHM_SHA256_LEADING_ZEROS = "sha256-leading-zeros-v1"

# The hardest work we are willing to do, mirroring proofofwork.MaxDifficulty in
# flashlight. A refusal threshold, not a setting: a server-side bug must not be
# able to wedge the overlay in a hash loop.
#
# The *usable* band is well below this. A challenge expires 60 seconds after it
# was minted, and the server checks that before it checks the work, so a
# difficulty CPython cannot finish inside the window never converges at all.
MAX_DIFFICULTY = 26

# Difficulties at or above this are logged. Around a million hashes takes a
# noticeable fraction of a second in CPython, and if we ever start paying that
# we want the record.
NOTEWORTHY_DIFFICULTY = 20

_DIGEST_BITS = 256


@dataclass(frozen=True, slots=True)
class Challenge:
    """A proof-of-work challenge handed out by flashlight"""

    # Opaque to us: signed and stateless server-side. Everything needed to solve
    # it is in the other two fields.
    challenge: str
    algorithm: str
    difficulty: int


def parse_challenge_response(response_json: object) -> Challenge:
    """Parse a proof-of-work challenge out of a challenge response"""
    if not isinstance(response_json, dict):
        raise AuthError(f"Invalid challenge response {response_json=}")

    challenge = response_json.get("challenge", None)
    if not isinstance(challenge, str) or not challenge:
        raise AuthError(f"Invalid challenge in challenge response {challenge=}")

    algorithm = response_json.get("algorithm", None)
    if not isinstance(algorithm, str) or not algorithm:
        raise AuthError(f"Invalid algorithm in challenge response {algorithm=}")

    difficulty = response_json.get("difficulty", None)
    if (
        isinstance(difficulty, bool)
        or not isinstance(difficulty, int)
        or difficulty < 0
    ):
        raise AuthError(f"Invalid difficulty in challenge response {difficulty=}")

    # `expiresInSeconds` is informational - we solve immediately, and the server
    # is the one that decides whether we made it in time.
    return Challenge(challenge=challenge, algorithm=algorithm, difficulty=difficulty)


def leading_zero_bits(digest: bytes) -> int:
    """Return the number of leading zero bits in the given digest"""
    return _DIGEST_BITS - int.from_bytes(digest, "big").bit_length()


@dataclass(frozen=True, slots=True)
class Solver:
    """A way to solve proof-of-work: solve(prefix, difficulty) -> solution"""

    name: str
    solve: Callable[[bytes, int], str]


# Fastest first
NATIVE_PREFERENCE = ("portable",)


def get_solver(name: str, library_path: Path = native_pow.LIBRARY_PATH) -> Solver:
    """
    Return the named solver: "python", "native" (the best native one), or a
    native implementation by name

    Raises AuthError if it can't be used. Never falls back to another solver.
    """
    if name == "python":
        return PYTHON_SOLVER

    if name != "native" and name not in native_pow.IMPLEMENTATIONS:
        raise AuthError(f"Unknown proof-of-work solver {name!r}")

    try:
        library = native_pow.NativeLibrary(library_path)
    except (OSError, native_pow.NativePowError) as e:
        raise AuthError(f"Could not load native solver from {library_path}") from e

    if name == "native":
        name = next((impl for impl in NATIVE_PREFERENCE if library.supported(impl)), "")
        if not name:
            raise AuthError("No native proof-of-work solver runs on this machine")
    elif not library.supported(name):
        raise AuthError(f"Native solver {name!r} is not supported on this machine")

    impl = name
    return Solver(
        name=impl,
        solve=lambda prefix, difficulty: library.solve(impl, prefix, difficulty),
    )


def pick_default_solver(library_path: Path = native_pow.LIBRARY_PATH) -> Solver:
    """Return the best native solver, falling back to the Python one"""
    try:
        return get_solver("native", library_path=library_path)
    except AuthError:
        logger.warning(
            "Native proof-of-work solver unavailable, falling back to Python",
            exc_info=True,
        )
        return PYTHON_SOLVER


@functools.cache
def default_solver() -> Solver:
    """Return the solver used for logging in, picked once per process"""
    solver = pick_default_solver()
    logger.info(f"Using proof-of-work solver {solver.name!r}")
    return solver


def self_test(name: str, difficulties: Iterable[int] = (0, 1, 8, 16, 20)) -> Solver:
    """
    Solve fresh challenges with the named solver and verify every solution

    `name` is as for `get_solver`. For "native" the default solver must also be
    that native solver - a login must not quietly use the Python fallback.
    Returns the solver. Raises AuthError on any failure.
    """
    solver = get_solver(name)

    if name == "native" and default_solver().name != solver.name:
        raise AuthError(
            f"The default solver is {default_solver().name!r}, not {solver.name!r}"
        )

    for difficulty in difficulties:
        # Lengths on both sides of the block boundaries, and a realistic one
        for length in (1, 43, 44, 63, 64, 341):
            challenge = Challenge(
                challenge=secrets.token_urlsafe(length)[:length],
                algorithm=ALGORITHM_SHA256_LEADING_ZEROS,
                difficulty=difficulty,
            )
            solution = solve_challenge(challenge, solver=solver)
            digest = hashlib.sha256(
                f"{challenge.challenge}:{solution}".encode()
            ).digest()
            if not solution or leading_zero_bits(digest) < difficulty:
                raise AuthError(
                    f"Solver {solver.name!r} gave a wrong solution {solution!r} "
                    f"to {challenge}"
                )

    return solver


def solve_challenge(challenge: Challenge, solver: Solver | None = None) -> str:
    """
    Return a solution to the given proof-of-work challenge

    Uses `default_solver()` unless `solver` is given.

    Must only ever be called from the auth thread - never from the UI thread or
    the game event path. At the difficulty the server asks for today this is a
    single hash, but the whole point of the mechanism is that the server can
    raise the number whenever it likes, without a client release.
    """
    if challenge.algorithm != ALGORITHM_SHA256_LEADING_ZEROS:
        raise AuthError(
            f"Unsupported proof-of-work algorithm {challenge.algorithm!r}. "
            f"This client only implements {ALGORITHM_SHA256_LEADING_ZEROS!r}."
        )

    if challenge.difficulty > MAX_DIFFICULTY:
        raise AuthError(
            f"Refusing proof-of-work difficulty {challenge.difficulty} - "
            f"this client works up to {MAX_DIFFICULTY}."
        )

    if challenge.difficulty >= NOTEWORTHY_DIFFICULTY:
        logger.warning(f"Solving proof-of-work at difficulty {challenge.difficulty}")

    if solver is None:
        solver = default_solver()

    try:
        return solver.solve(f"{challenge.challenge}:".encode(), challenge.difficulty)
    except native_pow.NativePowError as e:
        raise AuthError(f"Proof-of-work solver {solver.name!r} failed") from e


def difficulty_target(difficulty: int) -> bytes:
    """
    Return the bound a digest must be below to meet the given difficulty

    A big-endian digest has at least `difficulty` leading zero bits iff it is
    below 2**(256 - difficulty), and equal-length bytes compare like big-endian
    integers - so the check is a single bytes comparison.
    """
    if difficulty == 0:
        # 2**256 does not fit in 32 bytes. Every 32-byte digest is a prefix of,
        # and therefore less than, this.
        return b"\xff" * 33
    return (1 << (256 - difficulty)).to_bytes(32, "big")


_LOW_DIGITS = tuple(f"{low:03d}".encode() for low in range(1000))


def _solve_python(prefix: bytes, difficulty: int) -> str:
    # Candidates are str(high) + three digits. Hashing the prefix, and then each
    # high part, once and copying the state leaves one copy, update and digest
    # per attempt - which is what the interpreter spends its time on.
    # Every candidate is non-empty, as the server requires even at difficulty 0.
    target = difficulty_target(difficulty)
    base = hashlib.sha256(prefix)
    for high in itertools.count():
        high_part = str(high)
        with_high = base.copy()
        with_high.update(high_part.encode())
        copy = with_high.copy
        for low in _LOW_DIGITS:
            attempt = copy()
            attempt.update(low)
            if attempt.digest() < target:
                return high_part + low.decode()
    assert False, "unreachable"  # pragma: nocover


# Holds the GIL. The fallback when no native solver loads.
PYTHON_SOLVER = Solver(name="python", solve=_solve_python)
