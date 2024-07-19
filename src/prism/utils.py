import math
from collections import deque
from enum import Enum, unique
from pathlib import Path
from typing import Protocol, Self, TypeVar


class SupportsLT(Protocol):  # pragma: no cover
    def __lt__(self, other: Self) -> bool: ...


def read_key(key_file: Path) -> str:
    """Read the api key from the given file"""
    with key_file.open("r") as f:
        return f.read().strip()


def truncate_float(number: float, precision: int, *, extra_digits: int = 10) -> str:
    """Return the string (f) representation of number rounded down"""
    if not math.isfinite(number):
        # NaN and +-inf
        return str(number)

    if precision < 0:
        raise ValueError("Negative precision not supported")
    elif precision == 0:
        return str(int(number))

    # The result of the f-string is "{:.10f}" if precision + extra_digits == 10
    return f"{{:.{precision + extra_digits}f}}".format(number)[:-extra_digits]


def pluralize(word: str) -> str:
    """Return the simple pluralization of the given word"""
    return word + "s"


def div(dividend: float, divisor: float) -> float:
    """Divide two numbers, returning dividend if divisor is 0"""
    if dividend == 0:
        return 0.0
    elif divisor == 0:
        return dividend
    return dividend / divisor


Element = TypeVar("Element", bound=SupportsLT)


def insort_right(elements: deque[Element], new_element: Element) -> None:
    """
    Insert new_element into elements in sorted order

    elements must be sorted ascending
    If new_element is already in elements it will be inserted to the right
    NOTE: Assumes new_element is relatively large in elements
    """
    i = -1  # Init in case deque is empty
    # We assume new_element is large, so we do a linear search from the end
    for i, old_element in enumerate(reversed(elements)):
        # not < is equivalent to >=
        if not new_element < old_element:
            break
    else:
        # We fell off the left end of the array -> insert at the start
        i += 1

    elements.insert(len(elements) - i, new_element)


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

    @property
    def abbreviation(self) -> str:
        return self.text(False)[0]


NAME_MAP = {
    Time.SECOND: "second",
    Time.MINUTE: "minute",
    Time.HOUR: "hour",
    Time.DAY: "day",
    Time.MONTH: "month",
    Time.YEAR: "year",
}


def format_seconds(seconds: float) -> str:
    """
    Format the elapsed time in seconds as an integer amount of the largest denomination
    """
    for denomination in reversed(Time):
        count = int(seconds // denomination)
        if count:
            return f"{count} {denomination.text(count > 1)}"
    return f"{seconds:.2f} {Time.SECOND.text(True)}"


def format_seconds_short(seconds: float, decimals: int) -> str:
    """Format the elapsed time in a short format"""
    if seconds < 60:
        return "<1m"

    for denomination in (
        Time.YEAR,
        Time.DAY,
        Time.HOUR,
    ):
        count = seconds / denomination
        if count >= 1:
            break
    else:
        denomination = Time.MINUTE

    return (
        f"{truncate_float(seconds / denomination, decimals)}{denomination.abbreviation}"
    )
