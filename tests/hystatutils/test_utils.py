from typing import Union

import pytest

from hystatutils.utils import Time, div, format_seconds, pluralize  # TODO: read_key

Number = Union[int, float]
INF = float("inf")


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
        (10, 0, INF),
        (-10, 0, -INF),
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
    "seconds, text",
    (
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
