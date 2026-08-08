import hashlib
import logging
from dataclasses import dataclass

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

# Difficulties at or above this are logged. Around a million hashes takes about
# a second in CPython, and if we ever start paying that we want the record.
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


def solve_challenge(challenge: Challenge) -> str:
    """
    Return a solution to the given proof-of-work challenge

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

    prefix = f"{challenge.challenge}:".encode()

    # A non-empty solution is required even at difficulty 0, where the empty
    # string would be a perfectly valid proof - so we count from "0" rather than
    # special-casing the easy path away.
    counter = 0
    while True:
        solution = str(counter)
        digest = hashlib.sha256(prefix + solution.encode()).digest()
        if leading_zero_bits(digest) >= challenge.difficulty:
            return solution
        counter += 1
