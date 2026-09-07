import hashlib
import itertools
from collections.abc import Callable

import pytest

from prism.flashlight.auth.benchmark import (
    DEFAULT_RUNS,
    ESTIMATE_FROM,
    IMPERCEPTIBLE_UNTIL_SECONDS,
    NOTICEABLE_FROM_SECONDS,
    P95_FACTOR,
    P99_FACTOR,
    PAINFUL_FROM_SECONDS,
    VERDICT_EXPIRES,
    VERDICT_FINE,
    VERDICT_IMPERCEPTIBLE,
    VERDICT_NEVER,
    VERDICT_NOTICEABLE,
    VERDICT_PAINFUL,
    VERDICTS_IN_ORDER,
    BenchmarkSpec,
    Estimate,
    Run,
    estimate_difficulties,
    format_headline,
    format_report,
    format_seconds,
    hurts,
    mint_fake_challenge,
    parse_spec,
    run_benchmark,
    start_benchmark,
    summarize,
    time_one_solve,
    verdict_for,
)
from prism.flashlight.auth.proof_of_work import (
    ALGORITHM_SHA256_LEADING_ZEROS,
    MAX_DIFFICULTY,
    leading_zero_bits,
    solve_challenge,
)


def make_clock(*times: float) -> Callable[[], float]:
    """A clock returning the given readings, one per call"""
    readings = iter(times)
    return lambda: next(readings)


@pytest.mark.parametrize(
    "spec, result",
    (
        ("20", BenchmarkSpec(first=20, last=20, runs=DEFAULT_RUNS)),
        ("0", BenchmarkSpec(first=0, last=0, runs=DEFAULT_RUNS)),
        ("14-22", BenchmarkSpec(first=14, last=22, runs=DEFAULT_RUNS)),
        ("18x10", BenchmarkSpec(first=18, last=18, runs=10)),
        ("14-22x3", BenchmarkSpec(first=14, last=22, runs=3)),
        # A one-wide range is still a range
        ("18-18x1", BenchmarkSpec(first=18, last=18, runs=1)),
        (
            f"{MAX_DIFFICULTY}",
            BenchmarkSpec(first=MAX_DIFFICULTY, last=MAX_DIFFICULTY, runs=DEFAULT_RUNS),
        ),
    ),
)
def test_parse_spec(spec: str, result: BenchmarkSpec) -> None:
    assert parse_spec(spec) == result


@pytest.mark.parametrize(
    "spec",
    (
        "",
        "x",
        "x3",
        "-",
        "-20",
        "abc",
        "20x",
        "20xabc",
        "1.5",
        "20 22",
        # Falling range
        "22-14",
        # Negative
        "20x-1",
        "20x0",
        # Above what the solver will work on
        f"{MAX_DIFFICULTY + 1}",
        f"20-{MAX_DIFFICULTY + 1}",
    ),
)
def test_parse_spec_invalid(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_spec(spec)


def test_mint_fake_challenge() -> None:
    challenge = mint_fake_challenge(4)

    assert challenge.algorithm == ALGORITHM_SHA256_LEADING_ZEROS
    assert challenge.difficulty == 4

    # Shaped like flashlight's: a signed payload, a ".", and the signature
    payload, separator, signature = challenge.challenge.partition(".")
    assert separator == "."
    assert payload and signature

    # The length is the measurement - a real challenge spans several SHA-256
    # blocks, and a short stand-in would hash several times faster.
    assert 250 < len(challenge.challenge) < 400


def test_mint_fake_challenge_is_unique() -> None:
    """Two runs must not solve the same challenge"""
    assert mint_fake_challenge(0) != mint_fake_challenge(0)


def test_mint_fake_challenge_is_solvable() -> None:
    challenge = mint_fake_challenge(8)
    solution = solve_challenge(challenge)

    digest = hashlib.sha256(f"{challenge.challenge}:{solution}".encode()).digest()
    assert leading_zero_bits(digest) >= 8


def test_time_one_solve() -> None:
    run = time_one_solve(4, clock=make_clock(10.0, 12.5))

    assert run.difficulty == 4
    assert run.duration_seconds == 2.5
    # Every attempt from 0 up to and including the winning one
    assert run.hashes >= 1


def test_time_one_solve_counts_every_attempt() -> None:
    """Difficulty 0 is solved by the first counter value"""
    run = time_one_solve(0, clock=make_clock(0.0, 1.0))

    assert run.hashes == 1


def make_run(duration_seconds: float, hashes: int, difficulty: int = 18) -> Run:
    return Run(difficulty=difficulty, duration_seconds=duration_seconds, hashes=hashes)


def test_summarize() -> None:
    summary = summarize(
        18, (make_run(1.0, 1000), make_run(3.0, 5000), make_run(2.0, 3000))
    )

    assert summary.difficulty == 18
    assert summary.runs == 3
    assert summary.mean_seconds == 2.0
    assert summary.median_seconds == 2.0
    assert summary.min_seconds == 1.0
    assert summary.max_seconds == 3.0
    assert summary.mean_hashes == 3000
    assert summary.hashes_per_second == 9000 / 6.0


def test_summarize_unmeasurably_fast_runs() -> None:
    """A coarse clock reports no time at all, which is not infinite speed"""
    summary = summarize(0, (make_run(0.0, 1, difficulty=0),))

    assert summary.hashes_per_second != summary.hashes_per_second  # nan


@pytest.mark.parametrize(
    "mean_seconds, verdict",
    (
        # Judged on p95, which is ln(20) means
        (0.0, VERDICT_IMPERCEPTIBLE),
        (IMPERCEPTIBLE_UNTIL_SECONDS / P95_FACTOR, VERDICT_IMPERCEPTIBLE),
        (0.4, VERDICT_FINE),
        (NOTICEABLE_FROM_SECONDS / P95_FACTOR, VERDICT_FINE),
        (1.1, VERDICT_NOTICEABLE),
        (PAINFUL_FROM_SECONDS / P95_FACTOR, VERDICT_NOTICEABLE),
        (4.0, VERDICT_PAINFUL),
        # p95 past the budget: the handshake stops fitting the TTL
        (30 / P95_FACTOR, VERDICT_PAINFUL),
        (11.0, VERDICT_EXPIRES),
        (30.0, VERDICT_EXPIRES),
        # Not even the mean fits
        (31.0, VERDICT_NEVER),
        (600.0, VERDICT_NEVER),
    ),
)
def test_verdict_for(mean_seconds: float, verdict: str) -> None:
    assert verdict_for(mean_seconds, 30.0) == verdict


def test_verdict_for_is_monotonic() -> None:
    """More work is never a better verdict"""
    verdicts = [verdict_for(mean_seconds / 10, 30.0) for mean_seconds in range(1, 500)]
    indices = [VERDICTS_IN_ORDER.index(verdict) for verdict in verdicts]

    assert indices == sorted(indices)
    # And the whole scale is reachable
    assert set(verdicts) == set(VERDICTS_IN_ORDER)


@pytest.mark.parametrize(
    "verdict, hurting",
    (
        (VERDICT_IMPERCEPTIBLE, False),
        (VERDICT_FINE, False),
        (VERDICT_NOTICEABLE, True),
        (VERDICT_PAINFUL, True),
        (VERDICT_EXPIRES, True),
        (VERDICT_NEVER, True),
    ),
)
def test_hurts(verdict: str, hurting: bool) -> None:
    assert hurts(verdict) is hurting


def test_estimate_difficulties() -> None:
    estimates = estimate_difficulties(1_000_000, budget_seconds=30.0)

    assert [estimate.difficulty for estimate in estimates] == list(
        range(ESTIMATE_FROM, MAX_DIFFICULTY + 1)
    )

    # Each difficulty is twice the work of the one below it
    for lower, higher in itertools.pairwise(estimates):
        assert higher.mean_hashes == lower.mean_hashes * 2
        assert higher.mean_seconds == pytest.approx(lower.mean_seconds * 2)

    at_20 = estimates[20 - ESTIMATE_FROM]
    assert at_20.mean_hashes == 2**20
    assert at_20.mean_seconds == pytest.approx(1.048576)
    assert at_20.p95_seconds == pytest.approx(1.048576 * P95_FACTOR)
    assert at_20.p99_seconds == pytest.approx(1.048576 * P99_FACTOR)
    # A p95 of ~3.1s at a million hashes a second
    assert at_20.verdict == VERDICT_NOTICEABLE

    # It only ever gets worse across the band
    indices = [VERDICTS_IN_ORDER.index(estimate.verdict) for estimate in estimates]
    assert indices == sorted(indices)
    assert estimates[0].verdict == VERDICT_IMPERCEPTIBLE
    assert estimates[-1].verdict == VERDICT_NEVER


@pytest.mark.parametrize(
    "seconds, formatted",
    (
        (0.0, "0ms"),
        (0.0004, "0ms"),
        (0.5, "500ms"),
        (0.9999, "1000ms"),
        (1.0, "1.00s"),
        (12.345, "12.35s"),
        (600.0, "600.00s"),
    ),
)
def test_format_seconds(seconds: float, formatted: str) -> None:
    assert format_seconds(seconds) == formatted


def make_estimate(difficulty: int, verdict: str, p95_seconds: float = 1.0) -> Estimate:
    return Estimate(
        difficulty=difficulty,
        mean_hashes=2**difficulty,
        mean_seconds=p95_seconds / P95_FACTOR,
        p95_seconds=p95_seconds,
        p99_seconds=p95_seconds * P99_FACTOR / P95_FACTOR,
        verdict=verdict,
    )


def test_format_headline() -> None:
    headline = format_headline(
        (
            make_estimate(10, VERDICT_IMPERCEPTIBLE, 0.5),
            make_estimate(11, VERDICT_FINE, 2.0),
            make_estimate(12, VERDICT_NOTICEABLE, 4.0),
            make_estimate(13, VERDICT_PAINFUL, 12.0),
            make_estimate(14, VERDICT_EXPIRES, 40.0),
        )
    )

    assert "Starts to hurt at difficulty 12" in headline
    assert "4.00s" in headline
    # The last one that is free, and the last one that works at all
    assert "Difficulty 11 and under is free" in headline
    assert "Stops working entirely above 13" in headline


def test_format_headline_when_the_first_difficulty_already_hurts() -> None:
    headline = format_headline(
        (
            make_estimate(10, VERDICT_PAINFUL, 12.0),
            make_estimate(11, VERDICT_NEVER, 90.0),
        )
    )

    assert "Starts to hurt at difficulty 10" in headline
    assert "and under is free" not in headline
    assert "Stops working entirely above 10" in headline


def test_format_headline_when_nothing_hurts() -> None:
    headline = format_headline(
        (
            make_estimate(10, VERDICT_IMPERCEPTIBLE, 0.1),
            make_estimate(11, VERDICT_FINE, 2.0),
        )
    )

    assert "Nothing up to difficulty 11 hurts" in headline
    assert "2.00s" in headline


def test_format_headline_when_everything_is_broken() -> None:
    headline = format_headline((make_estimate(10, VERDICT_NEVER, 900.0),))

    assert "Starts to hurt at difficulty 10" in headline
    assert "Stops working" not in headline


def test_format_report() -> None:
    summaries = (
        summarize(18, (make_run(1.0, 250_000),)),
        summarize(19, (make_run(2.0, 500_000),)),
    )

    report = format_report(summaries, budget_seconds=30.0)

    # The answer comes first, before the working behind it
    assert report.strip().startswith("Starts to hurt at difficulty ")
    assert "Measured" in report
    # Both measured difficulties, and the whole estimated band
    for difficulty in (18, 19, *range(ESTIMATE_FROM, MAX_DIFFICULTY + 1)):
        assert f"\n{difficulty} " in report
    # Estimates come off the hardest difficulty measured
    assert "difficulty 19" in report
    assert VERDICT_IMPERCEPTIBLE in report
    assert VERDICT_NEVER in report


def test_format_report_without_results() -> None:
    assert format_report(()) == "No proof-of-work results to report."


def collect(reports: list[str]) -> Callable[[str], None]:
    return reports.append


def test_run_benchmark() -> None:
    reports: list[str] = []

    summaries = run_benchmark(
        BenchmarkSpec(first=0, last=2, runs=2), report=collect(reports)
    )

    assert [summary.difficulty for summary in summaries] == [0, 1, 2]
    assert all(summary.runs == 2 for summary in summaries)
    # One line per run, and no unreported warmup run inflating the rate
    assert len(reports) == 6
    assert reports[0].startswith("difficulty 0 run 1/2:")
    assert reports[-1].startswith("difficulty 2 run 2/2:")


def test_start_benchmark() -> None:
    reports: list[str] = []

    thread = start_benchmark(
        BenchmarkSpec(first=0, last=0, runs=1), report=collect(reports)
    )

    # Backgrounded, so the overlay keeps starting while it runs
    assert thread.daemon
    thread.join(timeout=30)
    assert not thread.is_alive()

    # The run line, then the whole report
    assert len(reports) == 2
    assert reports[0].startswith("difficulty 0 run 1/1:")
    assert "Measured" in reports[1]


def test_start_benchmark_reports_its_own_failure() -> None:
    """A benchmark that breaks must not take the overlay beside it down"""
    reports: list[str] = []

    def explode(line: str) -> None:
        if line.startswith("difficulty"):
            raise RuntimeError("boom")
        reports.append(line)

    thread = start_benchmark(BenchmarkSpec(first=0, last=0, runs=1), report=explode)
    thread.join(timeout=30)

    assert not thread.is_alive()
    assert reports == ["The proof-of-work benchmark failed - see the log for why."]


def test_run_benchmark_solves_real_challenges() -> None:
    """The benchmark measures the shipped solver, not a copy of it"""
    reports: list[str] = []

    summaries = run_benchmark(
        BenchmarkSpec(first=6, last=6, runs=1), report=collect(reports)
    )

    (summary,) = summaries
    assert summary.mean_hashes >= 1
    assert summary.hashes_per_second > 0
