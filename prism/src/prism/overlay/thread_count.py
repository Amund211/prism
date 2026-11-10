import logging
import os
from functools import cache

logger = logging.getLogger(__name__)


def get_cpu_count() -> int | None:
    """Return the amount of logical cores on the computer, None if failure"""
    try:
        return os.cpu_count()
    except OSError:  # pragma: no coverage
        logger.exception("Failed getting cpu count")
        return None


def recommend_stats_thread_count_from_cpu_count(cpu_count: int | None) -> int:
    """Recommend cpu_count restricted to [2, 16], 2 if failure"""
    if cpu_count is not None:
        # Restrict number of threads to [2, 16]
        return max(2, min(16, cpu_count))

    logger.warning("Failed getting cpu count, defaulting to 2 stats threads")
    return 2


@cache
def recommend_stats_thread_count() -> int:
    """Recommend an amount of concurrent stats thread for the current cpu"""
    return recommend_stats_thread_count_from_cpu_count(get_cpu_count())
