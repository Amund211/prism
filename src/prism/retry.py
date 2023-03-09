import logging
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


def execute_with_retry(f: Executor[T], retry_limit: int, timeout: float) -> T:
    """Retry the function until it doesn't raise an ExecutionError"""
    errors = []  # Store the errors

    for i in range(retry_limit):
        try:
            value = f(last_try=i + 1 == retry_limit)
        except ExecutionError as e:
            logger.warning(
                f"Function execution failed ({i+1}/{retry_limit})", exc_info=e
            )
            errors.append(e)
        else:
            return value

        time.sleep(timeout)  # Wait a bit before retrying

    raise ExecutionError(f"Multiple ({retry_limit}) executions failed: {errors}")
