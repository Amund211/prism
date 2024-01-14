from dataclasses import dataclass

import pytest

from prism.retry import ExecutionError, Executor, compute_backoff, execute_with_retry


@dataclass
class BackoffTestCase:
    initial_timeout: float
    backoff_multiplier: float
    retry_index: int


def make_fallible(failures: int) -> Executor[int]:
    failure_count = [0]

    def f(*, last_try: bool) -> int:
        if failure_count[0] < failures:
            failure_count[0] += 1
            raise ExecutionError

        return 1

    return f


@pytest.mark.parametrize(
    "test_case, expected",
    (
        (BackoffTestCase(initial_timeout=0, backoff_multiplier=2, retry_index=0), 0),
        (BackoffTestCase(initial_timeout=0, backoff_multiplier=2, retry_index=1), 0),
        (BackoffTestCase(initial_timeout=1, backoff_multiplier=2, retry_index=0), 1),
        (BackoffTestCase(initial_timeout=1, backoff_multiplier=2, retry_index=1), 2),
        (BackoffTestCase(initial_timeout=1, backoff_multiplier=2, retry_index=2), 4),
        (BackoffTestCase(initial_timeout=10, backoff_multiplier=3, retry_index=0), 10),
        (BackoffTestCase(initial_timeout=10, backoff_multiplier=3, retry_index=1), 30),
        (BackoffTestCase(initial_timeout=10, backoff_multiplier=3, retry_index=2), 90),
    ),
)
def test_compute_backoff(test_case: BackoffTestCase, expected: float) -> None:
    assert (
        compute_backoff(
            initial_timeout=test_case.initial_timeout,
            backoff_multiplier=test_case.backoff_multiplier,
            retry_index=test_case.retry_index,
        )
        == expected
    )


@pytest.mark.parametrize("failures", range(5))
def test_make_fallible(failures: int) -> None:
    f = make_fallible(failures)
    for i in range(failures):
        with pytest.raises(ExecutionError):
            f(last_try=False)
    assert f(last_try=False) == 1


@pytest.mark.parametrize("failures", range(5))
def test_execute_with_retry(failures: int) -> None:
    f = make_fallible(failures)
    assert execute_with_retry(f, retry_limit=5, initial_timeout=0) == 1


@pytest.mark.parametrize("failures", range(5, 10))
def test_execute_with_retry_failure(failures: int) -> None:
    f = make_fallible(failures)
    with pytest.raises(ExecutionError):
        execute_with_retry(f, retry_limit=5, initial_timeout=0)


@pytest.mark.parametrize("retry_limit", range(1, 10))
def test_execute_with_retry_last_try(retry_limit: int) -> None:
    """Assert that last_try is properly provided to the executor"""
    call_count = [0]

    def f(*, last_try: bool) -> int:
        call_count[0] += 1
        if last_try:
            assert call_count[0] == retry_limit
            return 1
        else:
            assert call_count[0] < retry_limit
            raise ExecutionError

    assert execute_with_retry(f, retry_limit=retry_limit, initial_timeout=0) == 1
