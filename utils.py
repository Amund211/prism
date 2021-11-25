from enum import Enum, unique
from typing import Union


def pluralize(word: str) -> str:
    """Return the simple pluralization of the given word"""
    return word + "s"


def div(dividend: Union[int, float], divisor: Union[int, float]) -> float:
    """Divide two numbers, returning INF if divisor is 0"""
    if dividend == 0:
        return 0
    elif divisor == 0:
        return float("inf") * (1 if dividend >= 0 else -1)
    return dividend / divisor


@unique
class Time(int, Enum):
    """
    Different denominations of time used for formatting

    NOTE: Define the denominations in strictly increasing order
    """

    SECOND = 1
    MINUTE = 60 * SECOND
    HOUR = 60 * MINUTE
    DAY = 24 * HOUR
    MONTH = 30 * DAY
    YEAR = 12 * MONTH

    def text(self, plural: bool) -> str:
        base = NAME_MAP[self]
        return pluralize(base) if plural else base


NAME_MAP = {
    Time.SECOND: "second",
    Time.MINUTE: "minute",
    Time.HOUR: "hour",
    Time.DAY: "day",
    Time.MONTH: "month",
    Time.YEAR: "year",
}


def format_seconds(seconds: Union[float, int]) -> str:
    """
    Format the elapsed time in seconds as an integer amount of the largest denomination
    """
    for denomination in reversed(Time):
        count = int(seconds // denomination)
        if count:
            return f"{count} {denomination.text(count > 1)}"
    return f"{seconds:.2f} {Time.SECOND.text(False)}"
