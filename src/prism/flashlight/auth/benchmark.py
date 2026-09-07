"""
Benchmark the proof-of-work solver

A calibration tool rather than part of the overlay: it answers what difficulty
flashlight can ask a machine like this one for, given that the whole handshake
has to fit inside a 60 second challenge TTL. Run it with `--test-pow`.

Nothing here talks to flashlight. The challenges are minted locally, in the
same shape the server mints them in.

Everything timed is the shipped code: `solve_challenge` as the auth thread
calls it, on a worker thread, at prod's constants, beside a running overlay.
Nothing here may make the solve faster than a login does - a benchmark that
outruns the real client reports a difficulty as affordable and hands users the
sluggishness.
"""

import base64
import json
import logging
import math
import secrets
import statistics
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from prism.flashlight.auth.proof_of_work import (
    ALGORITHM_SHA256_LEADING_ZEROS,
    MAX_DIFFICULTY,
    Challenge,
    solve_challenge,
)

logger = logging.getLogger(__name__)

# flashlight's challengeTTL. It is measured from minting, so both round trips
# and the solve come out of it - that, and not MAX_DIFFICULTY, is what caps the
# difficulty that actually works.
CHALLENGE_TTL_SECONDS = 60.0

# The share of the TTL we let the solve spend. The rest pays for the two round
# trips of the handshake.
SOLVE_BUDGET_FRACTION = 0.5

SOLVE_BUDGET_SECONDS = CHALLENGE_TTL_SECONDS * SOLVE_BUDGET_FRACTION

# Solve time is geometric in the number of attempts, so a mean says little on
# its own: the tail is what decides whether a difficulty is usable. For the
# exponential it approximates, p95 is ln(20) means and p99 is ln(100).
P95_FACTOR = math.log(20)
P99_FACTOR = math.log(100)

# What the wait costs the user, in seconds of p95 - the launch one user in
# twenty gets, not the average one. The overlay has no session until the
# handshake finishes, so this is dead time before the first stats can load.
#
# These are the numbers the whole benchmark exists to place a difficulty
# against. They are judgement calls about perception, not measurements:
# a second is under the threshold where a wait registers as a wait at all,
# three is where one is clearly there but excusable at startup, and ten is
# where a user starts wondering whether the overlay is broken.
IMPERCEPTIBLE_UNTIL_SECONDS = 1.0
NOTICEABLE_FROM_SECONDS = 3.0
PAINFUL_FROM_SECONDS = 10.0

# The band the estimate table covers. Below it the numbers are noise; above it
# is over flashlight's own ceiling.
ESTIMATE_FROM = 10

DEFAULT_RUNS = 3

VERDICT_IMPERCEPTIBLE = "imperceptible"
VERDICT_FINE = "fine"
VERDICT_NOTICEABLE = "noticeable"
VERDICT_PAINFUL = "painful"
VERDICT_EXPIRES = "unusable - the tail expires"
VERDICT_NEVER = "does not converge"

# Worst to best is the order that matters: a verdict is "at least as bad as"
# another one.
VERDICTS_IN_ORDER = (
    VERDICT_IMPERCEPTIBLE,
    VERDICT_FINE,
    VERDICT_NOTICEABLE,
    VERDICT_PAINFUL,
    VERDICT_EXPIRES,
    VERDICT_NEVER,
)

# The first verdict a user would actually feel. Everything from here up is the
# answer to "where does this start to hurt".
FIRST_HURTING_VERDICT = VERDICT_NOTICEABLE

# The verdicts that are not a cost but a failure: the handshake does not
# complete inside the TTL, so the client loops on challenges that expire.
BROKEN_VERDICTS = (VERDICT_EXPIRES, VERDICT_NEVER)


@dataclass(frozen=True, slots=True)
class BenchmarkSpec:
    """What to measure: every difficulty in [first, last], `runs` times each"""

    first: int
    last: int
    runs: int


def parse_spec(spec: str) -> BenchmarkSpec:
    """
    Parse a `FIRST[-LAST][xRUNS]` spec, e.g. "20", "14-22", "18x10", "14-22x3"

    Raises `ValueError` on anything else, including a difficulty above
    MAX_DIFFICULTY - the solver refuses those, so benchmarking them is not a
    thing we could do even if we wanted the number.
    """
    difficulties, times, runs_text = spec.partition("x")
    first_text, dash, last_text = difficulties.partition("-")

    try:
        first = int(first_text)
        # A trailing separator with nothing after it is a typo, not a default
        last = int(last_text) if dash else first
        runs = int(runs_text) if times else DEFAULT_RUNS
    except ValueError as e:
        raise ValueError(
            f"Invalid proof-of-work benchmark spec {spec!r}. "
            f"Expected FIRST[-LAST][xRUNS], e.g. 20, 14-22, 18x10, 14-22x3."
        ) from e

    if not 0 <= first <= last <= MAX_DIFFICULTY:
        raise ValueError(
            f"Invalid difficulty range {first}-{last} in benchmark spec {spec!r}. "
            f"Must be rising and within 0-{MAX_DIFFICULTY}."
        )

    if runs < 1:
        raise ValueError(f"Invalid run count {runs} in benchmark spec {spec!r}.")

    return BenchmarkSpec(first=first, last=last, runs=runs)


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def mint_fake_challenge(difficulty: int) -> Challenge:
    """
    Mint a challenge shaped like flashlight's, solvable without the server

    The shape matters for the measurement, not just for looks. Every attempt
    hashes `challenge:solution`, so the ~320 characters of a real challenge
    cost six SHA-256 blocks where a short stand-in would cost one - measuring
    against a short stand-in would overstate the hash rate several times over.
    """
    payload = json.dumps(
        {
            "nonce": _base64url(secrets.token_bytes(16)),
            "userId": str(uuid.uuid4()),
            "ipHash": secrets.token_hex(32),
            "issuedAtUnixMillis": int(time.time() * 1000),
            "difficulty": difficulty,
            "alg": ALGORITHM_SHA256_LEADING_ZEROS,
        },
        # Go's encoding/json emits no whitespace, and the length is the point
        separators=(",", ":"),
    ).encode()

    return Challenge(
        challenge=f"{_base64url(payload)}.{_base64url(secrets.token_bytes(32))}",
        algorithm=ALGORITHM_SHA256_LEADING_ZEROS,
        difficulty=difficulty,
    )


@dataclass(frozen=True, slots=True)
class Run:
    """One timed solve"""

    difficulty: int
    duration_seconds: float
    hashes: int


def time_one_solve(
    difficulty: int, clock: Callable[[], float] = time.perf_counter
) -> Run:
    """
    Solve one freshly minted fake challenge and time it

    `time.perf_counter` rather than `time.monotonic`: the coarse clock on
    Windows would report whole runs at the low difficulties as taking no time.
    """
    challenge = mint_fake_challenge(difficulty)

    start = clock()
    solution = solve_challenge(challenge)
    duration_seconds = clock() - start

    # The solver counts up from 0, so the winning counter is also the number of
    # attempts that missed before it.
    return Run(
        difficulty=difficulty,
        duration_seconds=duration_seconds,
        hashes=int(solution) + 1,
    )


@dataclass(frozen=True, slots=True)
class Summary:
    """The runs at one difficulty, reduced to the numbers worth reporting"""

    difficulty: int
    runs: int
    mean_seconds: float
    median_seconds: float
    min_seconds: float
    max_seconds: float
    mean_hashes: float
    hashes_per_second: float


def summarize(difficulty: int, runs: Sequence[Run]) -> Summary:
    """Summarize a non-empty sequence of runs at one difficulty"""
    durations = [run.duration_seconds for run in runs]
    hashes = [run.hashes for run in runs]
    total_seconds = sum(durations)

    return Summary(
        difficulty=difficulty,
        runs=len(runs),
        mean_seconds=statistics.fmean(durations),
        median_seconds=statistics.median(durations),
        min_seconds=min(durations),
        max_seconds=max(durations),
        mean_hashes=statistics.fmean(hashes),
        # A whole run can measure as no time at all on a coarse clock, and an
        # unmeasurably fast run is not an infinitely fast one.
        hashes_per_second=(
            sum(hashes) / total_seconds if total_seconds > 0 else math.nan
        ),
    )


def verdict_for(mean_seconds: float, budget_seconds: float) -> str:
    """
    What a difficulty costs the user whose client does the work

    Judged on p95, not on the mean. Solve time is geometric - anywhere from
    instant to several times the mean - so what a user carries away is their
    worst launches, and an average that looks fine hides them.
    """
    p95_seconds = mean_seconds * P95_FACTOR

    # The failures first: past the budget it stops being a wait and starts
    # being a handshake that cannot complete.
    if mean_seconds > budget_seconds:
        return VERDICT_NEVER
    if p95_seconds > budget_seconds:
        return VERDICT_EXPIRES

    if p95_seconds > PAINFUL_FROM_SECONDS:
        return VERDICT_PAINFUL
    if p95_seconds > NOTICEABLE_FROM_SECONDS:
        return VERDICT_NOTICEABLE
    if p95_seconds > IMPERCEPTIBLE_UNTIL_SECONDS:
        return VERDICT_FINE
    return VERDICT_IMPERCEPTIBLE


def hurts(verdict: str) -> bool:
    """Whether a user would feel a wait this long"""
    return VERDICTS_IN_ORDER.index(verdict) >= VERDICTS_IN_ORDER.index(
        FIRST_HURTING_VERDICT
    )


@dataclass(frozen=True, slots=True)
class Estimate:
    """What one difficulty would cost, extrapolated from a measured hash rate"""

    difficulty: int
    mean_hashes: int
    mean_seconds: float
    p95_seconds: float
    p99_seconds: float
    verdict: str


def estimate_difficulties(
    hashes_per_second: float, budget_seconds: float = SOLVE_BUDGET_SECONDS
) -> list[Estimate]:
    """Extrapolate the whole difficulty band from one measured hash rate"""
    estimates = []
    for difficulty in range(ESTIMATE_FROM, MAX_DIFFICULTY + 1):
        mean_hashes = 2**difficulty
        mean_seconds = mean_hashes / hashes_per_second
        estimates.append(
            Estimate(
                difficulty=difficulty,
                mean_hashes=mean_hashes,
                mean_seconds=mean_seconds,
                p95_seconds=mean_seconds * P95_FACTOR,
                p99_seconds=mean_seconds * P99_FACTOR,
                verdict=verdict_for(mean_seconds, budget_seconds),
            )
        )
    return estimates


def format_headline(estimates: Sequence[Estimate]) -> str:
    """
    Say where the difficulty starts to hurt

    The one line the benchmark exists to produce. Everything else in the report
    is the working behind it.
    """
    first_hurting = next(
        (estimate for estimate in estimates if hurts(estimate.verdict)), None
    )
    last_working = next(
        (
            estimate
            for estimate in reversed(estimates)
            if estimate.verdict not in BROKEN_VERDICTS
        ),
        None,
    )

    if first_hurting is None:
        top = estimates[-1]
        return (
            f"Nothing up to difficulty {top.difficulty} hurts on this machine - "
            f"p95 is still {format_seconds(top.p95_seconds)} at the ceiling."
        )

    parts = [
        f"Starts to hurt at difficulty {first_hurting.difficulty}: "
        f"p95 {format_seconds(first_hurting.p95_seconds)} "
        f"({first_hurting.verdict})."
    ]

    if first_hurting.difficulty > estimates[0].difficulty:
        below = estimates[estimates.index(first_hurting) - 1]
        parts.append(
            f"Difficulty {below.difficulty} and under is free "
            f"(p95 {format_seconds(below.p95_seconds)})."
        )

    if last_working is not None and last_working.difficulty >= first_hurting.difficulty:
        parts.append(f"Stops working entirely above {last_working.difficulty}.")

    return " ".join(parts)


def format_seconds(seconds: float) -> str:
    """Format a duration for the report"""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


def _row(cells: Sequence[str], widths: Sequence[int]) -> str:
    return "  ".join(
        cell.rjust(width) if index else cell.ljust(width)
        for index, (cell, width) in enumerate(zip(cells, widths, strict=True))
    )


_SUMMARY_WIDTHS = (4, 4, 9, 9, 9, 9, 12, 11)
_ESTIMATE_WIDTHS = (4, 12, 9, 9, 9, 28)


def format_summaries(summaries: Sequence[Summary]) -> list[str]:
    """Format the measured results as a table"""
    lines = [
        _row(
            ("diff", "runs", "mean", "median", "min", "max", "hashes", "rate"),
            _SUMMARY_WIDTHS,
        )
    ]
    for summary in summaries:
        lines.append(
            _row(
                (
                    str(summary.difficulty),
                    str(summary.runs),
                    format_seconds(summary.mean_seconds),
                    format_seconds(summary.median_seconds),
                    format_seconds(summary.min_seconds),
                    format_seconds(summary.max_seconds),
                    f"{summary.mean_hashes:,.0f}",
                    f"{summary.hashes_per_second / 1000:,.0f} kH/s",
                ),
                _SUMMARY_WIDTHS,
            )
        )
    return lines


def format_estimates(estimates: Sequence[Estimate]) -> list[str]:
    """Format the extrapolated difficulty band as a table"""
    lines = [
        _row(("diff", "hashes", "mean", "p95", "p99", "verdict"), _ESTIMATE_WIDTHS)
    ]
    for estimate in estimates:
        lines.append(
            _row(
                (
                    str(estimate.difficulty),
                    f"{estimate.mean_hashes:,}",
                    format_seconds(estimate.mean_seconds),
                    format_seconds(estimate.p95_seconds),
                    format_seconds(estimate.p99_seconds),
                    estimate.verdict,
                ),
                _ESTIMATE_WIDTHS,
            )
        )
    return lines


def format_report(
    summaries: Sequence[Summary], budget_seconds: float = SOLVE_BUDGET_SECONDS
) -> str:
    """
    Render the whole report

    The estimates come off the hardest difficulty measured: those are the runs
    where the hash loop, rather than the timing overhead, dominates.
    """
    if not summaries:
        return "No proof-of-work results to report."

    basis = summaries[-1]
    estimates = estimate_difficulties(basis.hashes_per_second, budget_seconds)

    return "\n".join(
        (
            "",
            format_headline(estimates),
            "",
            "Measured",
            *format_summaries(summaries),
            "",
            f"Estimated from {basis.hashes_per_second / 1000:,.0f} kH/s measured "
            f"at difficulty {basis.difficulty} over {basis.runs} run(s). Solve "
            f"time is geometric, so p95 is ~3x the mean and p99 ~4.6x. A verdict "
            f"is how the p95 wait reads to a user; the last two mean the "
            f"handshake no longer fits the "
            f"{budget_seconds:.0f}s of flashlight's "
            f"{CHALLENGE_TTL_SECONDS:.0f}s challenge TTL left for the solve.",
            *format_estimates(estimates),
        )
    )


def run_benchmark(spec: BenchmarkSpec, report: Callable[[str], None]) -> list[Summary]:
    """
    Measure every difficulty in the spec, reporting each run as it lands

    Call it from a worker thread - see `start_benchmark`.

    Deliberately unwarmed. A login solves exactly one challenge, cold, so a
    warmup run would exclude a cost the user really pays and report a
    difficulty as cheaper than it is.
    """
    summaries = []
    for difficulty in range(spec.first, spec.last + 1):
        runs = []
        for index in range(spec.runs):
            run = time_one_solve(difficulty)
            runs.append(run)
            report(
                f"difficulty {difficulty} "
                f"run {index + 1}/{spec.runs}: "
                f"{format_seconds(run.duration_seconds)} "
                f"({run.hashes:,} hashes)"
            )
        summaries.append(summarize(difficulty, runs))
    return summaries


def start_benchmark(
    spec: BenchmarkSpec,
    report: Callable[[str], None],
    budget_seconds: float = SOLVE_BUDGET_SECONDS,
) -> threading.Thread:
    """
    Start the benchmark on a background thread and return it, already running

    Not joined, so the caller goes on to run the overlay: the point of running
    both is that the hash loop competes for the GIL with the tkinter thread and
    the stats threads, exactly as a real login's solve does.

    A worker thread rather than the main one for the same reason.
    `solve_challenge` is auth-thread-only in the overlay, and the thread is
    what decides who the loop shares the interpreter with.

    A daemon, so closing the overlay does not wait for a sweep to finish.
    """

    def target() -> None:
        try:
            summaries = run_benchmark(spec, report)
        except BaseException:
            # The benchmark is a diagnostic running beside the real overlay. It
            # reports its own failure and leaves everything else alone.
            logger.exception("The proof-of-work benchmark failed")
            report("The proof-of-work benchmark failed - see the log for why.")
            return
        report(format_report(summaries, budget_seconds))

    thread = threading.Thread(target=target, daemon=True, name="prism-pow-benchmark")
    thread.start()
    return thread
