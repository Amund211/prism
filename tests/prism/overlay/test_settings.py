import dataclasses
from pathlib import Path
from typing import Any

import pytest

from prism.overlay.keybinds import (
    AlphanumericKey,
    AlphanumericKeyDict,
    KeyDict,
    SpecialKey,
    SpecialKeyDict,
)
from prism.overlay.output.cells import ColumnName
from prism.overlay.output.config import RatingConfigCollectionDict
from prism.overlay.settings import (
    PLACEHOLDER_API_KEY,
    NickValue,
    Settings,
    SettingsDict,
    ValueType,
    fill_missing_settings,
    get_boolean_setting,
    get_settings,
    value_or_default,
)
from tests.prism.overlay.utils import (
    CUSTOM_RATING_CONFIG_COLLECTION,
    CUSTOM_RATING_CONFIG_COLLECTION_DICT,
    DEFAULT_RATING_CONFIG_COLLECTION,
    DEFAULT_RATING_CONFIG_COLLECTION_DICT,
    make_settings,
)

KEY_IF_MISSING = "KEY_IF_MISSING"


def make_settings_dict(
    hypixel_api_key: str | None = None,
    antisniper_api_key: str | None = None,
    use_antisniper_api: bool | None = None,
    column_order: tuple[ColumnName, ...] | None = None,
    rating_configs: RatingConfigCollectionDict | None = None,
    known_nicks: dict[str, NickValue] | None = None,
    autodenick_teammates: bool | None = None,
    autoselect_logfile: bool | None = None,
    show_on_tab: bool | None = None,
    show_on_tab_keybind: KeyDict | None = None,
    check_for_updates: bool | None = None,
    hide_dead_players: bool | None = None,
    disable_overrideredirect: bool | None = None,
    hide_with_alpha: bool | None = None,
    alpha_hundredths: int | None = None,
) -> SettingsDict:
    """Make a settings dict with default values if missing"""
    return {
        "hypixel_api_key": value_or_default(hypixel_api_key, default=KEY_IF_MISSING),
        "antisniper_api_key": value_or_default(
            antisniper_api_key, default=PLACEHOLDER_API_KEY
        ),
        "use_antisniper_api": value_or_default(use_antisniper_api, default=False),
        "column_order": value_or_default(
            column_order, default=("username", "stars", "fkdr", "winstreak")
        ),
        "rating_configs": value_or_default(
            rating_configs, default=DEFAULT_RATING_CONFIG_COLLECTION_DICT
        ),
        "known_nicks": value_or_default(known_nicks, default={}),
        "autodenick_teammates": value_or_default(autodenick_teammates, default=True),
        "autoselect_logfile": value_or_default(autoselect_logfile, default=True),
        "show_on_tab": value_or_default(show_on_tab, default=True),
        # mypy thinks this is {"name": str}, when it really is just KeyDict
        "show_on_tab_keybind": value_or_default(  # type: ignore [typeddict-item]
            show_on_tab_keybind,
            default=SpecialKeyDict(name="tab", vk=None, key_type="special"),
        ),
        "check_for_updates": value_or_default(check_for_updates, default=True),
        "hide_dead_players": value_or_default(hide_dead_players, default=True),
        "disable_overrideredirect": value_or_default(
            disable_overrideredirect, default=False
        ),
        "hide_with_alpha": value_or_default(hide_with_alpha, default=False),
        "alpha_hundredths": value_or_default(alpha_hundredths, default=80),
    }


def get_api_key() -> str:
    return KEY_IF_MISSING


PLACEHOLDER_PATH = Path("PLACEHOLDER_PATH")

settings_to_dict_cases: tuple[tuple[Settings, SettingsDict], ...] = (
    (
        Settings(
            hypixel_api_key="my-key",
            antisniper_api_key="my-key",
            use_antisniper_api=True,
            column_order=("username", "winstreak", "stars"),
            rating_configs=DEFAULT_RATING_CONFIG_COLLECTION,
            known_nicks={"AmazingNick": {"uuid": "123987", "comment": "Player1"}},
            autodenick_teammates=True,
            autoselect_logfile=True,
            show_on_tab=True,
            show_on_tab_keybind=AlphanumericKey(name="a", char="a"),
            check_for_updates=True,
            hide_dead_players=True,
            disable_overrideredirect=True,
            hide_with_alpha=True,
            alpha_hundredths=80,
            path=PLACEHOLDER_PATH,
        ),
        {
            "hypixel_api_key": "my-key",
            "antisniper_api_key": "my-key",
            "use_antisniper_api": True,
            "column_order": ("username", "winstreak", "stars"),
            "rating_configs": DEFAULT_RATING_CONFIG_COLLECTION_DICT,
            "known_nicks": {"AmazingNick": {"uuid": "123987", "comment": "Player1"}},
            "autodenick_teammates": True,
            "autoselect_logfile": True,
            "show_on_tab": True,
            "show_on_tab_keybind": AlphanumericKeyDict(
                name="a", char="a", key_type="alphanumeric"
            ),
            "check_for_updates": True,
            "hide_dead_players": True,
            "disable_overrideredirect": True,
            "hide_with_alpha": True,
            "alpha_hundredths": 80,
        },
    ),
    (
        Settings(
            hypixel_api_key="my-other-key",
            antisniper_api_key="my-other-key",
            use_antisniper_api=False,
            column_order=("username", "stars", "fkdr", "wlr", "winstreak"),
            rating_configs=CUSTOM_RATING_CONFIG_COLLECTION,
            known_nicks={},
            autodenick_teammates=False,
            autoselect_logfile=False,
            show_on_tab=False,
            show_on_tab_keybind=SpecialKey(name="tab", vk=None),
            check_for_updates=False,
            hide_dead_players=False,
            disable_overrideredirect=False,
            hide_with_alpha=False,
            alpha_hundredths=30,
            path=PLACEHOLDER_PATH,
        ),
        {
            "hypixel_api_key": "my-other-key",
            "antisniper_api_key": "my-other-key",
            "use_antisniper_api": False,
            "column_order": ("username", "stars", "fkdr", "wlr", "winstreak"),
            "rating_configs": CUSTOM_RATING_CONFIG_COLLECTION_DICT,
            "known_nicks": {},
            "autodenick_teammates": False,
            "autoselect_logfile": False,
            "show_on_tab": False,
            "show_on_tab_keybind": SpecialKeyDict(
                name="tab", vk=None, key_type="special"
            ),
            "check_for_updates": False,
            "hide_dead_players": False,
            "disable_overrideredirect": False,
            "hide_with_alpha": False,
            "alpha_hundredths": 30,
        },
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
    "settings_dict, result", tuple((t[1], t[0]) for t in settings_to_dict_cases)
)
def test_settings_update_from(settings_dict: SettingsDict, result: Settings) -> None:
    settings = Settings.from_dict(make_settings_dict(), path=PLACEHOLDER_PATH)
    settings.update_from(settings_dict)
    assert settings == result


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
    value: ValueType | None, default: ValueType, result: ValueType
) -> None:
    assert value_or_default(value, default=default) == result


@pytest.mark.parametrize("settings, settings_dict", settings_to_dict_cases)
def test_read_and_write_settings(
    settings: Settings, settings_dict: SettingsDict, tmp_path: Path
) -> None:
    # Make a copy so we can mutate it
    settings = dataclasses.replace(settings)

    settings.path = tmp_path / "settings.toml"
    settings.flush_to_disk()

    # NOTE: We can no longer do this since we store some null values in the dictionary
    #       which just get stored as missing keys in the toml
    # read_settings_dict = read_settings(settings.path)
    # assert read_settings_dict == settings_dict

    assert get_settings(settings.path, get_api_key) == settings


def test_read_missing_settings_file(tmp_path: Path) -> None:
    # Assert that get_settings doesn't fail when file doesn't exist
    empty_path = tmp_path / "settings2.toml"
    assert get_settings(empty_path, get_api_key) == Settings.from_dict(
        source=make_settings_dict(), path=empty_path
    )


def test_flush_settings_from_controller(tmp_path: Path) -> None:
    from prism.overlay.controller import RealOverlayController
    from prism.overlay.nick_database import NickDatabase
    from tests.prism.overlay.utils import create_state

    settings = make_settings(hypixel_api_key="my-key", path=tmp_path / "settings.toml")

    # File not found
    assert get_settings(settings.path, get_api_key) != settings

    controller = RealOverlayController(
        state=create_state(), settings=settings, nick_database=NickDatabase([{}])
    )

    controller.store_settings()

    # File properly stored
    assert get_settings(settings.path, get_api_key) == settings


def test_get_boolean_setting() -> None:
    # The key is present
    assert (False, False) == get_boolean_setting(
        {"key": False}, "key", False, default=True
    )
    assert (False, True) == get_boolean_setting(
        {"key": False}, "key", True, default=True
    )

    # The key is missing
    assert (True, True) == get_boolean_setting({}, "key", False, default=True)
    assert (True, True) == get_boolean_setting({}, "key", True, default=True)

    assert (False, True) == get_boolean_setting({}, "key", False, default=False)


fill_settings_test_cases: tuple[tuple[dict[str, Any], SettingsDict, bool], ...] = (
    (
        {
            "hypixel_api_key": "my-key",
            "antisniper_api_key": "my-key",
            "use_antisniper_api": False,
            "column_order": ("username", "stars", "fkdr", "wlr"),
            "rating_configs": CUSTOM_RATING_CONFIG_COLLECTION_DICT,
            "known_nicks": {"AmazingNick": {"uuid": "123987", "comment": "Player1"}},
            "autodenick_teammates": False,
            "autoselect_logfile": False,
            "show_on_tab": False,
            "show_on_tab_keybind": SpecialKeyDict(
                name="somekey", vk=123456, key_type="special"
            ),
            "check_for_updates": False,
            "hide_dead_players": False,
            "disable_overrideredirect": True,
            "hide_with_alpha": True,
            "alpha_hundredths": 40,
        },
        make_settings_dict(
            hypixel_api_key="my-key",
            antisniper_api_key="my-key",
            use_antisniper_api=False,
            column_order=("username", "stars", "fkdr", "wlr"),
            rating_configs=CUSTOM_RATING_CONFIG_COLLECTION_DICT,
            known_nicks={"AmazingNick": {"uuid": "123987", "comment": "Player1"}},
            autodenick_teammates=False,
            autoselect_logfile=False,
            show_on_tab=False,
            show_on_tab_keybind=SpecialKeyDict(
                name="somekey", vk=123456, key_type="special"
            ),
            check_for_updates=False,
            hide_dead_players=False,
            disable_overrideredirect=True,
            hide_with_alpha=True,
            alpha_hundredths=40,
        ),
        False,
    ),
    (
        {"hypixel_api_key": "my-key"},
        make_settings_dict(hypixel_api_key="my-key"),
        True,
    ),
    (
        {"hypixel_api_key": 1},
        make_settings_dict(),
        True,
    ),
    (
        {"hypixel_api_key": None},
        make_settings_dict(),
        True,
    ),
    (
        {
            "hypixel_api_key": {},
            "known_nicks": {"AmazingNick": {"uuid": "123987", "comment": "Player1"}},
        },
        make_settings_dict(
            known_nicks={"AmazingNick": {"uuid": "123987", "comment": "Player1"}}
        ),
        True,
    ),
    (
        {"antisniper_api_key": None},
        make_settings_dict(),
        True,
    ),
    (
        {"hypixel_api_key": "my-key", "use_antisniper_api": True},
        make_settings_dict(hypixel_api_key="my-key", use_antisniper_api=True),
        True,
    ),
    # Placeholder key
    (
        {"hypixel_api_key": PLACEHOLDER_API_KEY},
        make_settings_dict(),
        True,
    ),
    # Key too short
    (
        {"hypixel_api_key": "k"},
        make_settings_dict(),
        True,
    ),
    (
        {"antisniper_api_key": "k"},
        make_settings_dict(),
        True,
    ),
    # No settings
    ({}, make_settings_dict(), True),
    # Corrupt data in known_nicks
    (
        {
            "hypixel_api_key": "my-key",
            "known_nicks": {
                # Key is not a string
                1234: {"uuid": 123987, "comment": "Player1"}
            },
        },
        make_settings_dict(hypixel_api_key="my-key"),
        True,
    ),
    (
        {
            "hypixel_api_key": "my-key",
            "known_nicks": {
                # Value is a string, not a dict
                "AmazingNick": "uuid"
                "123987"
                "comment"
                "Player1"
            },
        },
        make_settings_dict(hypixel_api_key="my-key"),
        True,
    ),
    (
        {
            "hypixel_api_key": "my-key",
            "known_nicks": {
                # Incorrect type on uuid or comment
                "AmazingNick": {"uuid": 123987, "comment": "Player1"}
            },
        },
        make_settings_dict(hypixel_api_key="my-key"),
        True,
    ),
    (
        {
            "hypixel_api_key": "my-key",
            "known_nicks": {
                # Incorrect type on uuid or comment
                "AmazingNick": {"uuid": "123987", "comment": 1234}
            },
        },
        make_settings_dict(hypixel_api_key="my-key"),
        True,
    ),
    (
        {
            "hypixel_api_key": "my-key",
            # Alpha tenths out of range
            "alpha_hundredths": 1000,
        },
        make_settings_dict(hypixel_api_key="my-key"),
        True,
    ),
    (
        {
            "hypixel_api_key": "my-key",
            # Alpha tenths out of range
            "alpha_hundredths": 5,
        },
        make_settings_dict(hypixel_api_key="my-key"),
        True,
    ),
    (
        # Invalid type for keybind
        {"show_on_tab_keybind": 5},
        make_settings_dict(),
        True,
    ),
    (
        # Invalid key type for keybind
        {
            "show_on_tab_keybind": {
                "key_type": "invalid",
                "char": "a",
                "vk": 1,
                "name": "name",
            }
        },
        make_settings_dict(),
        True,
    ),
    (
        # Invalid data for special key
        {"show_on_tab_keybind": {"key_type": "special", "vk": "badvk", "name": "name"}},
        make_settings_dict(),
        True,
    ),
    (
        # Invalid data for alphanumeric key
        {
            "show_on_tab_keybind": {
                "key_type": "alphanumeric",
                "char": 1234,
                "name": "name",
            }
        },
        make_settings_dict(),
        True,
    ),
    (
        # Invalid data for autoselect_logfile
        {"autoselect_logfile": "yes"},
        make_settings_dict(),
        True,
    ),
    (
        # Invalid data for autodenick_teammates
        {"autodenick_teammates": "yes"},
        make_settings_dict(),
        True,
    ),
    (
        # Invalid data for column_order
        {"column_order": "yes"},
        make_settings_dict(),
        True,
    ),
    (
        # No column names
        {"column_order": ()},
        make_settings_dict(),
        True,
    ),
    (
        # No valid column names
        {"column_order": ("lkjdlfkj", "lksdjlskdjlskd", "a", "", 1, {}, [])},
        make_settings_dict(),
        True,
    ),
    (
        # Some invalid column names
        {"column_order": ("username", "stars", "lkjdlfkj", "", 1, {}, [])},
        make_settings_dict(column_order=("username", "stars")),
        True,
    ),
)


@pytest.mark.parametrize(
    "incomplete_settings, result_dict, result_updated", fill_settings_test_cases
)
def test_fill_missing_settings(
    incomplete_settings: dict[str, Any], result_dict: SettingsDict, result_updated: bool
) -> None:
    settings_dict, settings_updated = fill_missing_settings(
        incomplete_settings, get_api_key
    )
    assert settings_dict == result_dict
    assert settings_updated == result_updated
