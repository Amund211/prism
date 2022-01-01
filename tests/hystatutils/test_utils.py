from collections import deque
from pathlib import Path
from typing import Union

import pytest

from hystatutils.utils import (
    Element,
    Time,
    div,
    format_seconds,
    insort_right,
    pluralize,
    read_key,
)

Number = Union[int, float]
INF = float("inf")


@pytest.mark.parametrize(
    "file_content, key",
    (
        ("my_key", "my_key"),
        ("my_key\n", "my_key"),
        ("\nmy_key\n\n\t\n", "my_key"),
    ),
)
def test_read_key(file_content: str, key: str, tmp_path: Path) -> None:
    key_path = tmp_path / "api_key"
    key_path.write_text(file_content)
    assert read_key(key_path) == key


@pytest.mark.parametrize(
    "word, plural",
    (
        ("second", "seconds"),
        ("minute", "minutes"),
        ("hour", "hours"),
        ("day", "days"),
        ("month", "months"),
        ("year", "years"),
        ("apple", "apples"),
        ("banana", "bananas"),
        ("wolf", "wolfs"),  # Only the simple form is used
    ),
)
def test_pluralize(word: str, plural: str) -> None:
    assert pluralize(word) == plural


@pytest.mark.parametrize(
    "dividend, divisor, quotient",
    (
        (10.0, 1, 10.0),
        (10.0, 1.0, 10.0),
        (10, 1.0, 10.0),
        (10, 1, 10.0),
        (0.1, 0, INF),
        (10, 0, INF),
        (-10, 0, -INF),
        (-0.1, 0, -INF),
        (0, 0, 0.0),
        (0, 1, 0.0),
        (0, 1, 0.0),
    ),
)
def test_div(dividend: Number, divisor: Number, quotient: Number) -> None:
    result = div(dividend, divisor)

    assert result == quotient
    assert type(result) is type(quotient)


@pytest.mark.parametrize(
    "elements, new_element, result",
    (
        (deque([1, 2, 3]), 0.5, deque([0.5, 1, 2, 3])),
        (deque([1, 2, 3]), 1.5, deque([1, 1.5, 2, 3])),
        (deque([1, 2, 3]), 2.5, deque([1, 2, 2.5, 3])),
        (deque([1, 2, 3]), 3.5, deque([1, 2, 3, 3.5])),
    ),
)
def test_insort_right(
    elements: deque[Element], new_element: Element, result: deque[Element]
) -> None:
    insort_right(elements, new_element)
    assert elements == result


def test_insort_right_property() -> None:
    """Assert that the inserted element is to the right of an equal element"""

    class Comparable:
        def __init__(self, value: float) -> None:
            self.value = value

        def __lt__(self, other: "Comparable") -> bool:
            return self.value < other.value

    elements = deque([Comparable(1), Comparable(2), Comparable(3)])
    new_element = Comparable(3)
    insort_right(elements, new_element)

    assert elements[2].value == elements[3].value
    assert elements[2] is not new_element
    assert elements[3] is new_element


@pytest.mark.parametrize(
    "seconds, text",
    (
        (0, "0.00 seconds"),
        (0.1234, "0.12 seconds"),
        (0.991, "0.99 seconds"),
        (0.999, "1.00 seconds"),  # Float formatting performs rounding
        (Time.SECOND, "1 second"),
        (40 * Time.SECOND, "40 seconds"),
        (Time.MINUTE, "1 minute"),
        (13 * Time.MINUTE, "13 minutes"),
        (Time.HOUR, "1 hour"),
        (16 * Time.HOUR, "16 hours"),
        (75 * Time.HOUR, "3 days"),
        (Time.DAY, "1 day"),
        (20 * Time.DAY, "20 days"),
        (30 * Time.DAY, "1 month"),
        (Time.MONTH, "1 month"),
        (5 * Time.MONTH, "5 months"),
        (12 * Time.MONTH, "1 year"),
        (2 * 12 * Time.MONTH, "2 years"),
        (Time.YEAR, "1 year"),
        (2 * Time.YEAR, "2 years"),
        (123 * Time.YEAR, "123 years"),
    ),
)
def test_format_seconds(seconds: Number, text: str) -> None:
    assert format_seconds(seconds) == text
