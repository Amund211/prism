import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from tests.tabcap_fixtures import REPORT_KEY


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("tabcap", "tabcap fixtures (tests/tabcap_fixtures.py)")
    group.addoption(
        "--tabcap",
        choices=("train", "test", "all"),
        default=None,
        help=(
            "Run the tabcap fixture tests on this split. train: per-image results "
            "(use this for algorithm work). test: only the summary scores. "
            "all: both, on all fixtures."
        ),
    )
    group.addoption(
        "--tabcap-update",
        action="store_true",
        help="Write the current per-image results as the expected results",
    )


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    lines = config.stash.get(REPORT_KEY, [])
    if lines:
        terminalreporter.section("tabcap scores")
        for line in lines:
            terminalreporter.write_line(line)


@pytest.fixture(scope="session")
def data_directory() -> Path:
    """Create and return a Path to the persistent data directory"""
    data_dir = Path(__file__).parent / "data"

    if not data_dir.is_dir():
        data_dir.mkdir()

    return data_dir


@pytest.fixture(scope="session")
def technoblade_playerdata(data_directory: Path) -> Mapping[str, object]:
    """Return example playerdata for technoblade"""
    with (data_directory / "technoblade_2022_06_10.json").open("r") as f:
        response = json.load(f)

    assert response["success"]
    return cast(Mapping[str, object], response["player"])


@pytest.fixture(scope="session")
def ares_playerdata(data_directory: Path) -> Mapping[str, object]:
    """Return weird playerdata"""
    with (data_directory / "ares_2023_01_30.json").open("r") as f:
        response = json.load(f)

    assert response["success"]
    return cast(Mapping[str, object], response["player"])


@pytest.fixture(scope="session")
def seeecret_playerdata(data_directory: Path) -> Mapping[str, object]:
    """Return playerdata for Seeecret"""
    with (data_directory / "seeecret_2023_05_14.json").open("r") as f:
        response = json.load(f)

    assert response["success"]
    return cast(Mapping[str, object], response["player"])
