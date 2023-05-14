import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest


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
