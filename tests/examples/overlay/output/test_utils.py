from collections.abc import Sequence
from typing import Union

import pytest

from examples.overlay.output.utils import rate_value

LEVELS = (0.1, 0.5, 1, 10, 100)

# Tuples (value, rating) wrt LEVELS
test_cases: tuple[tuple[float, int], ...] = (
    (0, 0),
    (0.0, 0),
    (0.05, 0),
    (0.1, 1),
    (0.2, 1),
    (0.49, 1),
    (0.50, 2),
    (0.70, 2),
    (1, 3),
    (1.0, 3),
    (1.5, 3),
    (5, 3),
    (10, 4),
    (50, 4),
    (50.1, 4),
    (100, 5),
    (1000, 5),
    (float("inf"), 5),
    (-1, 0),
    (-float("inf"), 0),
)


@pytest.mark.parametrize("value, rating", test_cases)
def test_rate_value(
    value: Union[int, float], rating: int, levels: Sequence[Union[int, float]] = LEVELS
) -> None:
    """Assert that rate_value functions properly"""
    assert rate_value(value, levels) == rating
