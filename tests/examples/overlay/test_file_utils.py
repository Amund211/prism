import datetime
import unittest.mock
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, cast

import pytest

from examples.overlay.file_utils import watch_file_with_reopen
from tests.examples.overlay.mock_utils import (
    EndFileTest,
    Line,
    MockedFile,
    MockedPath,
    MockedTime,
    create_mocked_file,
)

REOPEN_TIMEOUT = 30
POLL_TIMEOUT = 0.1
# Due to floating point math, the read delay can be slightly longer that the poll-time
MAX_DELAY = POLL_TIMEOUT * 1.1


def get_seen_lines(
    lines: Sequence[Line],
    amt_opens: int,
    start_at: int,
    blocking: Literal[True, False],
    start: datetime.datetime = datetime.datetime(2022, 1, 1, 12),
) -> tuple[list[str | None], list[float], MockedPath, MockedFile, MockedTime]:
    mocked_path, mocked_file, mocked_time = create_mocked_file(lines, amt_opens, start)

    seen: list[str | None] = []
    timestamps: list[float] = []

    with (
        unittest.mock.patch("examples.overlay.file_utils.time", mocked_time.time),
        unittest.mock.patch(
            "examples.overlay.file_utils.datetime", mocked_time.datetime
        ),
        unittest.mock.patch("examples.overlay.file_utils.date", mocked_time.date),
    ):
        with pytest.raises(EndFileTest):
            for line in watch_file_with_reopen(
                cast(Path, mocked_path),
                start_at=start_at,
                blocking=blocking,
                reopen_timeout=REOPEN_TIMEOUT,
                poll_timeout=POLL_TIMEOUT,
            ):
                seen.append(line)
                timestamps.append(mocked_time.time.monotonic())

    return seen, timestamps, mocked_path, mocked_file, mocked_time


def assert_reads_in_time(timestamps: Sequence[float], targets: Sequence[float]) -> None:
    """Assert that all the reads were done at the expected time"""
    assert all(
        target - MAX_DELAY < timestamp < target + MAX_DELAY
        for timestamp, target in zip(timestamps, targets, strict=True)
    ), f"{timestamps=} {targets=}"


def test_mocked_file() -> None:
    """Basic sanity checks for the mocked file implementation"""
    mocked_path, mocked_file, mocked_time = create_mocked_file(
        [Line(0, "0"), Line(1, None), Line(2, "2")], amt_opens=2
    )

    with mocked_path.open() as f:
        assert f.readline() == "0\n"
        assert f.readline() == ""
        assert f.readline() == ""
        mocked_time.time.sleep(1)
        assert f.readline() == ""
        mocked_time.time.sleep(1)
        assert f.readline() == ""

    with mocked_path.open() as f:
        assert f.readline() == "2\n"

    mocked_path, mocked_file, mocked_time = create_mocked_file(
        [Line(0, "0"), Line(1, None), Line(2, "2")], amt_opens=2
    )

    mocked_time.time.sleep(2)

    with mocked_path.open() as f:
        assert f.readline() == "2\n"
        assert f.readline() == ""

    with mocked_path.open() as f:
        assert f.readline() == "2\n"


def test_simple_reads() -> None:
    seen, timestamps, mocked_path, mocked_file, mocked_time = get_seen_lines(
        [Line(t, "text") for t in range(5)], amt_opens=1, start_at=0, blocking=True
    )
    assert seen == ["text\n"] * 5
    assert_reads_in_time(timestamps, range(5))


def test_simple_reads_with_reopen() -> None:
    seen, timestamps, mocked_path, mocked_file, mocked_time = get_seen_lines(
        [Line(0, "first"), Line(31, "after")], amt_opens=2, start_at=0, blocking=True
    )
    assert seen == ["first\n", "after\n"]
    assert_reads_in_time(timestamps, [0, 31])


def test_read_after_clear() -> None:
    seen, timestamps, mocked_path, mocked_file, mocked_time = get_seen_lines(
        [Line(t, "text") for t in range(5)]
        + [Line(5, None)]
        + [Line(t + 5, f"new text{t}") for t in range(4)],
        amt_opens=2,
        start_at=0,
        blocking=True,
    )
    assert seen == ["text\n"] * 5 + [f"new text{t}\n" for t in range(4)]
    assert_reads_in_time(timestamps, [0, 1, 2, 3, 4, 34, 34, 34, 34])


def test_read_after_clear_after_midnight() -> None:
    seen, timestamps, mocked_path, mocked_file, mocked_time = get_seen_lines(
        [Line(0, "Old text")] * 10
        + [
            Line(1, None),  # Clear at midnight
            Line(1, "New text"),
            Line(2, "More new text"),
            Line(10, "Later text"),
        ],
        amt_opens=2,
        start_at=0,
        blocking=True,
        start=datetime.datetime(2022, 2, 1, 23, 59, 59),
    )
    assert seen == ["Old text\n"] * 10 + [
        "New text\n",
        "More new text\n",
        "Later text\n",
    ]
    assert_reads_in_time(timestamps, [0] * 10 + [7, 7, 10])


def test_simple_reads_non_blocking() -> None:
    seen, timestamps, mocked_path, mocked_file, mocked_time = get_seen_lines(
        [Line(t, "text") for t in range(5)], amt_opens=1, start_at=0, blocking=False
    )
    assert list(filter(lambda line: line is not None, seen)) == ["text\n"] * 5

    read_cycle = [0.0] + [i * 0.1 for i in range(10)]
    targets: list[float] = sum(
        ([c + second for c in read_cycle] for second in range(5)), start=[]
    ) + [i * 0.1 for i in range(50, 340)]
    assert_reads_in_time(timestamps, targets)
