import json
from pathlib import Path
from typing import Any, cast

import pytest


@pytest.fixture(scope="session")
def data_directory() -> Path:
    """Create and return a Path to the persistent data directory"""
    data_dir = Path(__file__).parent / "data"

    if not data_dir.is_dir():
        data_dir.mkdir()

    return data_dir


@pytest.fixture(scope="session")
def technoblade_playerdata(data_directory: Path) -> dict[str, Any]:
    """Return example playerdata for technoblade"""
    with (data_directory / "technoblade_2022_06_10.json").open("r") as f:
        response = json.load(f)

    assert response["success"]
    return cast(dict[str, Any], response["player"])
