import datetime
import unittest.mock
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, cast

import pytest

from prism.overlay.file_utils import watch_file_with_reopen
from tests.mock_utils import (
    EndFileTest,
    Line,
    MockedFile,
    MockedPath,
    MockedTime,
    create_mocked_file,
)

# NOTE: These are different that the defaults
# They are also kept as integers to avoid any floating point inaccuracies
REOPEN_TIMEOUT = 10
POLL_TIMEOUT = 1


def get_seen_lines(
    lines: Sequence[Line],
    amt_opens: int,
    start_at: int,
    blocking: Literal[True, False],
    start: datetime.datetime = datetime.datetime(2022, 1, 1, 12),
    reopen_timeout: int = REOPEN_TIMEOUT,
    poll_timeout: int = POLL_TIMEOUT,
) -> tuple[list[str | None], list[float], MockedPath, MockedFile, MockedTime]:
    mocked_path, mocked_file, mocked_time = create_mocked_file(lines, amt_opens, start)

    seen: list[str | None] = []
    timestamps: list[float] = []

    with (
        unittest.mock.patch("prism.overlay.file_utils.time", mocked_time.time),
        unittest.mock.patch("prism.overlay.file_utils.datetime", mocked_time.datetime),
        unittest.mock.patch("prism.overlay.file_utils.date", mocked_time.date),
    ):
        with pytest.raises(EndFileTest):
            for line in watch_file_with_reopen(
                cast(Path, mocked_path),
                start_at=start_at,
                blocking=blocking,
                reopen_timeout=reopen_timeout,
                poll_timeout=poll_timeout,
            ):
                seen.append(line)
                timestamps.append(mocked_time.time.monotonic())

    return seen, timestamps, mocked_path, mocked_file, mocked_time


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
    assert timestamps == list(range(5))


def test_simple_reads_with_reopen() -> None:
    seen, timestamps, mocked_path, mocked_file, mocked_time = get_seen_lines(
        [Line(0, "first"), Line(11, "after")], amt_opens=2, start_at=0, blocking=True
    )
    assert seen == ["first\n", "after\n"]
    assert timestamps == [0, 11]
    assert [call[0] for call in mocked_path.calls] == [0, 10]


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
    assert timestamps == [0, 1, 2, 3, 4, 14, 14, 14, 14]
    assert [call[0] for call in mocked_path.calls] == [0, 14]


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
    assert timestamps == [0] * 10 + [6, 6, 10]
    assert [call[0] for call in mocked_path.calls] == [0, 6]


def test_long_delay_before_midnight() -> None:
    """We don't want to reopen the file right after midnight"""
    seen, timestamps, mocked_path, mocked_file, mocked_time = get_seen_lines(
        [Line(0, "Old text")] * 10
        + [
            Line(59, None),  # Clear at midnight
            Line(59, "New text"),
            Line(60, "More new text"),
            Line(61, "Later text"),
        ],
        amt_opens=2,
        start_at=0,
        blocking=True,
        start=datetime.datetime(2022, 2, 1, 23, 59, 1),
        reopen_timeout=60,  # NOTE: longer timeout
    )
    assert seen == ["Old text\n"] * 10 + [
        "New text\n",
        "More new text\n",
        "Later text\n",
    ]
    assert timestamps == [0] * 10 + [64, 64, 64]
    assert [call[0] for call in mocked_path.calls] == [0, 64]


def test_simple_reads_non_blocking() -> None:
    seen, timestamps, mocked_path, mocked_file, mocked_time = get_seen_lines(
        [Line(t, "text") for t in range(5)], amt_opens=1, start_at=0, blocking=False
    )

    assert seen == ["text\n", None] * 5 + [None] * 9
    assert timestamps == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4] + list(range(5, 14))


def test_start_at() -> None:
    seen, timestamps, mocked_path, mocked_file, mocked_time = get_seen_lines(
        [Line(0, "Old text")] * 10 + [Line(1, "New text")] * 10,
        amt_opens=1,
        start_at=10,
        blocking=True,
    )
    assert seen == ["New text\n"] * 10
    assert timestamps == [1] * 10
