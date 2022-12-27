from collections.abc import Callable

import pytest

from prism.retry import ExecutionError, execute_with_retry


def make_fallible(failures: int) -> Callable[[], int]:
    failure_count = [0]

    def f() -> int:
        if failure_count[0] < failures:
            failure_count[0] += 1
            raise ExecutionError

        return 1

    return f


@pytest.mark.parametrize("failures", range(5))
def test_make_fallible(failures: int) -> None:
    f = make_fallible(failures)
    for i in range(failures):
        with pytest.raises(ExecutionError):
            f()
    assert f() == 1


@pytest.mark.parametrize("failures", range(5))
def test_execute_with_retry(failures: int) -> None:
    f = make_fallible(failures)
    assert execute_with_retry(f, retry_limit=5, timeout=0) == 1


@pytest.mark.parametrize("failures", range(5, 10))
def test_execute_with_retry_failure(failures: int) -> None:
    f = make_fallible(failures)
    with pytest.raises(ExecutionError):
        execute_with_retry(f, retry_limit=5, timeout=0)
