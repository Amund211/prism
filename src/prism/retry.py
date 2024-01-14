import logging
import random
import time
from typing import Protocol, TypeVar

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    pass


T = TypeVar("T", covariant=True)


class Executor(Protocol[T]):  # pragma: no coverage
    """Protocol for functions passed to execute_with_retry"""

    def __call__(self, *, last_try: bool) -> T:
        raise NotImplementedError


def compute_backoff(
    initial_timeout: float, backoff_multiplier: float, retry_index: int
) -> float:
    """
    Compute the exponential backoff for a given retry index

    Retry index starts at 0
    """
    assert backoff_multiplier >= 1
    assert retry_index >= 0

    return initial_timeout * backoff_multiplier**retry_index


def execute_with_retry(
    f: Executor[T],
    retry_limit: int,
    initial_timeout: float,
    backoff_multiplier: int = 2,
) -> T:
    """
    Retry the function until it doesn't raise an ExecutionError

    Uses exponential backoff with jitter
    """
    errors = []  # Store the errors

    for i in range(retry_limit):
        last_try = i + 1 == retry_limit
        try:
            value = f(last_try=last_try)
        except ExecutionError as e:
            logger.warning(
                f"Function execution failed ({i+1}/{retry_limit})", exc_info=e
            )
            errors.append(e)
        else:
            return value

        if not last_try:
            jitter_factor = random.uniform(0.75, 1.25)
            time.sleep(
                jitter_factor * compute_backoff(initial_timeout, backoff_multiplier, i)
            )

    raise ExecutionError(f"Multiple ({retry_limit}) executions failed: {errors}")
