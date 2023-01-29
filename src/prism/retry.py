import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    pass


T = TypeVar("T")


def execute_with_retry(f: Callable[[], T], retry_limit: int, timeout: float) -> T:
    """Retry the function until it doesn't raise an ExecutionError"""
    errors = []  # Store the errors

    for i in range(retry_limit):
        try:
            value = f()
        except ExecutionError as e:
            logger.warning(
                f"Function execution failed ({i+1}/{retry_limit})", exc_info=e
            )
            errors.append(e)
        else:
            return value

        time.sleep(timeout)  # Wait a bit before retrying

    raise ExecutionError(f"Multiple ({retry_limit}) executions failed: {errors}")
