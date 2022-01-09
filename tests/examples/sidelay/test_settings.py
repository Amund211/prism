from copy import copy
from pathlib import Path
from typing import Any, Optional

import pytest

from examples.sidelay.settings import (
    PLACEHOLDER_API_KEY,
    Settings,
    SettingsDict,
    ValueType,
    fill_missing_settings,
    get_settings,
    read_settings,
    value_or_default,
)

KEY_IF_MISSING = "KEY_IF_MISSING"


def get_api_key() -> str:
    return KEY_IF_MISSING


PLACEHOLDER_PATH = Path("PLACEHOLDER_PATH")

settings_to_dict_cases = (
    (
        Settings(hypixel_api_key="my-key", path=PLACEHOLDER_PATH),
        {"hypixel_api_key": "my-key"},
    ),
)


@pytest.mark.parametrize("settings, result", settings_to_dict_cases)
def test_settings_to_dict(settings: Settings, result: SettingsDict) -> None:
    assert settings.to_dict() == result


@pytest.mark.parametrize(
    "settings_dict, result", tuple((t[1], t[0]) for t in settings_to_dict_cases)
)
def test_settings_from_dict(settings_dict: SettingsDict, result: Settings) -> None:
    assert Settings.from_dict(settings_dict, path=PLACEHOLDER_PATH) == result


@pytest.mark.parametrize(
    "value, default, result",
    (
        (None, 1, 1),
        (2, 1, 2),
        (None, 1.0, 1.0),
        ("str", 1.0, "str"),
        (None, "default", "default"),
        ("test", "default", "test"),
        (None, None, None),
        ("str", None, "str"),
    ),
)
def test_value_or_default(
    value: Optional[ValueType], default: ValueType, result: ValueType
) -> None:
    assert value_or_default(value, default=default) == result


@pytest.mark.parametrize("settings, settings_dict", settings_to_dict_cases)
def test_read_and_write_settings(
    settings: Settings, settings_dict: SettingsDict, tmp_path: Path
) -> None:
    # Make a copy so we can mutate it
    settings = copy(settings)

    settings.path = tmp_path / "settings.toml"
    settings.flush_to_disk()

    read_settings_dict = read_settings(settings.path)

    assert read_settings_dict == settings_dict

    assert get_settings(settings.path, get_api_key) == settings

    # Assert that get_settings doesn't fail when file doesn't exist
    empty_path = tmp_path / "settings2.toml"
    assert get_settings(empty_path, get_api_key) == Settings(
        hypixel_api_key=KEY_IF_MISSING, path=empty_path
    )


@pytest.mark.parametrize(
    "incomplete_settings, result",
    (
        ({"hypixel_api_key": "my-key"}, {"hypixel_api_key": "my-key"}),
        ({"hypixel_api_key": 1}, {"hypixel_api_key": KEY_IF_MISSING}),
        ({"hypixel_api_key": None}, {"hypixel_api_key": KEY_IF_MISSING}),
        ({"hypixel_api_key": {}}, {"hypixel_api_key": KEY_IF_MISSING}),
        # Placeholder key
        ({"hypixel_api_key": PLACEHOLDER_API_KEY}, {"hypixel_api_key": KEY_IF_MISSING}),
        # Key too short
        ({"hypixel_api_key": "k"}, {"hypixel_api_key": KEY_IF_MISSING}),
        ({}, {"hypixel_api_key": KEY_IF_MISSING}),
    ),
)
def test_fill_missing_settings(
    incomplete_settings: dict[str, Any], result: SettingsDict
) -> None:

    assert fill_missing_settings(incomplete_settings, get_api_key) == result
