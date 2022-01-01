from collections import deque
from enum import Enum, unique
from pathlib import Path
from typing import Any, Protocol, TypeVar, Union


class SupportsLT(Protocol):  # pragma: no cover
    def __lt__(self, other: Any) -> bool:
        ...


def read_key(key_file: Path) -> str:
    """Read the api key from the given file"""
    with key_file.open("r") as f:
        return f.read().strip()


def pluralize(word: str) -> str:
    """Return the simple pluralization of the given word"""
    return word + "s"


def div(dividend: Union[int, float], divisor: Union[int, float]) -> float:
    """Divide two numbers, returning INF if divisor is 0"""
    if dividend == 0:
        return 0.0
    elif divisor == 0:
        return float("inf") * (1 if dividend >= 0 else -1)
    return dividend / divisor


Element = TypeVar("Element", bound=SupportsLT)


def insort_right(elements: deque[Element], new_element: Element) -> None:
    """
    Insert new_element into elements in sorted order

    elements must be sorted ascending
    If new_element is already in elements it will be inserted to the right
    NOTE: Assumes new_element is relatively large in elements
    """
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
    return f"{seconds:.2f} {Time.SECOND.text(True)}"
