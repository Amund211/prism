import datetime
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any


class EndFileTest(Exception):
    """Exception raised when a file-mock test should end"""

    pass


@dataclass
class _MockedTimeModule:
    """Class mocking the time module"""

    parent: "MockedTime"

    def sleep(self, seconds: float) -> None:
        """Mock time.sleep"""
        self.parent.current_time += seconds
        self.parent.current_datetime += datetime.timedelta(seconds=seconds)

    def monotonic(self) -> float:
        """Mock time.monotonic"""
        return self.parent.current_time


@dataclass
class _MockedDateTime:
    """Class mocking datetime.datetime"""

    parent: "MockedTime"

    def now(self) -> datetime.datetime:
        """Mock datetime.datetime.now"""
        return self.parent.current_datetime


@dataclass
class _MockedDate:
    """Class mocking datetime.date"""

    parent: "MockedTime"

    def today(self) -> datetime.date:
        """Mock datetime.date.today"""
        return self.parent.current_datetime.date()


class MockedTime:
    """Class mocking time-related functionality"""

    def __init__(self, start: datetime.datetime) -> None:
        self.current_time = 0.0
        self.current_datetime = start

        self.time = _MockedTimeModule(self)
        self.datetime = _MockedDateTime(self)
        self.date = _MockedDate(self)


@dataclass
class Line:
    time: float  # The time the line was written
    content: str | None  # The line of text (no \n) or None to clear the file


class MockedFile:
    """Class mocking an opened file"""

    def __init__(self, lines: Sequence[Line], mocked_time: MockedTime) -> None:
        assert all(
            l1.time <= l2.time for l1, l2 in zip(lines[:-1], lines[1:], strict=True)
        ), "Line timestamps must be sorted"

        self.mocked_time = mocked_time
        self.lines = lines

        self.contents: list[str] = []
        self.content_index = 0

    def __enter__(self) -> "MockedFile":
        """Enable context manager functionality"""
        # Seek to start of file when opening
        self.seek(0, os.SEEK_SET)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Enable context manager functionality"""
        pass

    def _set_contents(self) -> None:
        """
        Set the contents of the file based on the time and given lines

        NOTE: Unread lines on file clear will be lost, like with a real file
        """
        self.contents.clear()

        for line in self.lines:
            if line.time > self.mocked_time.time.monotonic():
                # This and further lines are in the future
                break

            if line.content is None:
                self.contents.clear()
            else:
                self.contents.append(f"{line.content}\n")

    def readline(self) -> str:
        """Mocked readline"""
        self._set_contents()

        if self.content_index >= len(self.contents):
            return ""

        line = self.contents[self.content_index]
        self.content_index += 1

        return line

    def tell(self) -> int:
        """Mocked tell"""
        return self.content_index

    def seek(self, offset: int, whence: int) -> None:
        """Mocked seek"""
        self._set_contents()

        if whence == os.SEEK_SET:  # 0
            self.content_index = offset
        elif whence == os.SEEK_CUR:  # 1
            self.content_index += offset
        elif whence == os.SEEK_END:  # 2
            self.content_index = len(self.contents) + offset
        else:
            raise ValueError(f"{whence=} is invalid")


class MockedPath:
    """Class mocking a path, returning a MockedFile"""

    def __init__(
        self, file: MockedFile, amt_opens: int, mocked_time: MockedTime
    ) -> None:
        self.file = file
        self.opens_remaining = amt_opens
        self.mocked_time = mocked_time
        self.calls: list[tuple[float, tuple[Any, ...], dict[str, Any]]] = []

    def open(self, *args: Any, **kwargs: Any) -> MockedFile:
        """Mocked open"""
        self.opens_remaining -= 1

        if self.opens_remaining < 0:
            raise EndFileTest

        self.calls.append((self.mocked_time.time.monotonic(), args, kwargs))
        return self.file


def create_mocked_time(
    start: datetime.datetime = datetime.datetime(2022, 1, 1, 12)
) -> tuple[Path, MockedPath]:
    pass


def create_mocked_file(
    lines: Sequence[Line],
    amt_opens: int,
    start: datetime.datetime = datetime.datetime(2022, 1, 1, 12),
) -> tuple[MockedPath, MockedFile, MockedTime]:
    mocked_time = MockedTime(start)
    mocked_file = MockedFile(lines, mocked_time)
    mocked_path = MockedPath(mocked_file, amt_opens, mocked_time)
    return mocked_path, mocked_file, mocked_time
