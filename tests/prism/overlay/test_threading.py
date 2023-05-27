import pytest

from prism.overlay.threading import (
    get_cpu_count,
    recommend_stats_thread_count,
    recommend_stats_thread_count_from_cpu_count,
)


def test_get_cpu_count() -> None:
    cpu_count = get_cpu_count()
    assert isinstance(cpu_count, int)


def test_recommend_stats_thread_count() -> None:
    stats_thread_count = recommend_stats_thread_count()
    assert isinstance(stats_thread_count, int)
    assert 2 <= stats_thread_count <= 16


@pytest.mark.parametrize(
    "cpu_count, stats_thread_count",
    (
        (None, 2),
        (1, 2),
        (2, 2),
        (3, 3),
        (4, 4),
        (12, 12),
        (16, 16),
        (18, 16),
        (20, 16),
        (128, 16),
    ),
)
def test_recommend_stats_thread_count_from_cpu_count(
    cpu_count: int | None, stats_thread_count: int
) -> None:
    assert recommend_stats_thread_count_from_cpu_count(cpu_count) == stats_thread_count
