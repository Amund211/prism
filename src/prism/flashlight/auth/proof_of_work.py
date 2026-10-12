import functools
import hashlib
import itertools
import logging
import math
import secrets
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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

# There is no difficulty cap. The limit is time: a challenge is only accepted
# until it expires, so we stop there, and faster hardware can do more work.
# This is also what stops a server-side bug from wedging the overlay in a hash
# loop.
DEFAULT_CHALLENGE_TTL_SECONDS = 60.0
# Guards a bad expiresInSeconds from the server
MAX_SOLVE_SECONDS = 120.0
# Kept back from the TTL for the login round trip
LOGIN_MARGIN_SECONDS = 5.0
MIN_SOLVE_SECONDS = 10.0

# CPU time that a user feels as a slow start. High, so that a later "slow" popup
# fires only when the solve really was slow.
SLOW_SOLVE_CPU_SECONDS = 5.0

_DIGEST_BITS = 256


@dataclass(frozen=True, slots=True)
class Challenge:
    """A proof-of-work challenge handed out by flashlight"""

    # Opaque to us: signed and stateless server-side. Everything needed to solve
    # it is in the other fields.
    challenge: str
    algorithm: str
    difficulty: int
    expires_in_seconds: float


class Deadline:
    """Expires when the monotonic or the wall clock is `seconds` in the future"""

    # The wall clock too: the server's TTL is wall time, and Linux's monotonic
    # clock stops during suspend. A solve that was suspended past the TTL stops
    # at its next check. The monotonic clock covers the wall clock going back.
    def __init__(
        self,
        seconds: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self._monotonic = monotonic
        self._wall = wall
        self._monotonic_at = monotonic() + seconds
        self._wall_at = wall() + seconds

    def expired(self) -> bool:
        return self._monotonic() >= self._monotonic_at or self._wall() >= self._wall_at


class DeadlineLike(Protocol):  # pragma: nocover
    def expired(self) -> bool: ...


class SolveTimeout(Exception):
    """A solver passed its deadline after `hashes` attempts"""

    def __init__(self, hashes: int) -> None:
        super().__init__(f"Deadline passed after {hashes} hashes")
        self.hashes = hashes


@dataclass(frozen=True, slots=True)
class SolveReport:
    """How a solve went. `solution` is None when it timed out."""

    solution: str | None
    difficulty: int
    solver: str
    solver_version: str
    hashes: int
    # What the user waited. Includes time in suspend on some platforms.
    elapsed_seconds: float
    # CPU time of the solving thread. Does not advance in suspend.
    cpu_seconds: float

    @property
    def slow(self) -> bool:
        """True if this machine needed a noticeable time for the work"""
        return self.cpu_seconds >= SLOW_SOLVE_CPU_SECONDS


class ProofOfWorkTimeoutError(AuthError):
    """The solve passed the deadline. Retrying with a new challenge can work."""

    def __init__(self, report: SolveReport) -> None:
        super().__init__(
            f"Proof-of-work at difficulty {report.difficulty} timed out after "
            f"{report.elapsed_seconds:.1f}s ({report.cpu_seconds:.1f}s CPU, "
            f"{report.hashes} hashes, solver {report.solver!r})"
        )
        self.report = report


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
        or difficulty > _DIGEST_BITS
    ):
        raise AuthError(f"Invalid difficulty in challenge response {difficulty=}")

    # Only sizes our time budget - the server decides if we made it in time - so
    # a bad value falls back rather than failing the login.
    expires_in_seconds = response_json.get("expiresInSeconds", None)
    if (
        isinstance(expires_in_seconds, bool)
        or not isinstance(expires_in_seconds, (int, float))
        or not 0 < expires_in_seconds < math.inf
    ):
        expires_in_seconds = DEFAULT_CHALLENGE_TTL_SECONDS

    return Challenge(
        challenge=challenge,
        algorithm=algorithm,
        difficulty=difficulty,
        expires_in_seconds=expires_in_seconds,
    )


def leading_zero_bits(digest: bytes) -> int:
    """Return the number of leading zero bits in the given digest"""
    return _DIGEST_BITS - int.from_bytes(digest, "big").bit_length()


@dataclass(frozen=True, slots=True)
class Solver:
    """
    A way to solve proof-of-work: solve(prefix, difficulty, deadline) -> solution

    The solution is the number of attempts before it, in decimal. Raises
    SolveTimeout when the deadline passes.
    """

    name: str
    # Reported to flashlight. Changes when the code's performance may change.
    version: str
    solve: Callable[[bytes, int, DeadlineLike], str]


# Fastest first
NATIVE_PREFERENCE = ("sha-ni", "armv8", "portable")


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

    def solve(prefix: bytes, difficulty: int, deadline: DeadlineLike) -> str:
        try:
            return library.solve(impl, prefix, difficulty, should_stop=deadline.expired)
        except native_pow.SolveStopped as e:
            raise SolveTimeout(e.hashes) from e

    try:
        version = library.version(impl)
    except native_pow.NativePowError as e:
        raise AuthError(f"Native solver {impl!r} has no version") from e

    return Solver(name=impl, version=str(version), solve=solve)


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
                expires_in_seconds=DEFAULT_CHALLENGE_TTL_SECONDS,
            )
            solution = solve_challenge(challenge, solver=solver).solution
            digest = hashlib.sha256(
                f"{challenge.challenge}:{solution}".encode()
            ).digest()
            if not solution or leading_zero_bits(digest) < difficulty:
                raise AuthError(
                    f"Solver {solver.name!r} gave a wrong solution {solution!r} "
                    f"to {challenge}"
                )

    return solver


def solve_budget(challenge: Challenge) -> float:
    """Return how many seconds we may spend solving the given challenge"""
    ttl = min(challenge.expires_in_seconds, MAX_SOLVE_SECONDS)
    return max(ttl - LOGIN_MARGIN_SECONDS, MIN_SOLVE_SECONDS)


def solve_challenge(
    challenge: Challenge,
    solver: Solver | None = None,
    deadline: DeadlineLike | None = None,
) -> SolveReport:
    """
    Solve the given proof-of-work challenge, and report how it went

    Uses `default_solver()` unless `solver` is given, and a deadline from
    `solve_budget` unless `deadline` is given. Raises ProofOfWorkTimeoutError,
    with the report, when the deadline passes.

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

    if solver is None:
        solver = default_solver()
    if deadline is None:
        deadline = Deadline(solve_budget(challenge))

    logger.info(
        f"Solving proof-of-work at difficulty {challenge.difficulty} "
        f"with solver {solver.name!r}"
    )
    started = time.monotonic()
    cpu_started = time.thread_time()

    def report(solution: str | None, hashes: int) -> SolveReport:
        return SolveReport(
            solution=solution,
            difficulty=challenge.difficulty,
            solver=solver.name,
            solver_version=solver.version,
            hashes=hashes,
            elapsed_seconds=time.monotonic() - started,
            cpu_seconds=time.thread_time() - cpu_started,
        )

    prefix = f"{challenge.challenge}:".encode()
    try:
        solution = solver.solve(prefix, challenge.difficulty, deadline)
    except SolveTimeout as e:
        timed_out = report(None, e.hashes)
        logger.warning(f"Proof-of-work timed out: {timed_out}")
        raise ProofOfWorkTimeoutError(timed_out) from e
    except native_pow.NativePowError as e:
        raise AuthError(f"Proof-of-work solver {solver.name!r} failed") from e

    result = report(solution, int(solution) + 1)
    if result.slow:
        logger.warning(f"Slow proof-of-work: {result}")
    else:
        logger.info(f"Solved proof-of-work: {result}")
    return result


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

# High parts per deadline check: 256k hashes, ~65 ms
PYTHON_BATCH_HIGHS = 256
PYTHON_BATCH_HASHES = PYTHON_BATCH_HIGHS * len(_LOW_DIGITS)


def _solve_python(prefix: bytes, difficulty: int, deadline: DeadlineLike) -> str:
    # Candidates are str(high) + three digits. Hashing the prefix, and then each
    # high part, once and copying the state leaves one copy, update and digest
    # per attempt - which is what the interpreter spends its time on.
    # Every candidate is non-empty, as the server requires even at difficulty 0.
    target = difficulty_target(difficulty)
    base = hashlib.sha256(prefix)
    for batch in itertools.count():
        if deadline.expired():
            raise SolveTimeout(batch * PYTHON_BATCH_HASHES)
        first = batch * PYTHON_BATCH_HIGHS
        for high in range(first, first + PYTHON_BATCH_HIGHS):
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
# Bump on any change to _solve_python or PYTHON_BATCH_HIGHS that may affect its
# performance. Flashlight's knownSolverVersions must allow it first.
PYTHON_SOLVER_VERSION = "1"

PYTHON_SOLVER = Solver(
    name="python", version=PYTHON_SOLVER_VERSION, solve=_solve_python
)
