import dataclasses
import io
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO
from unittest import mock

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
    assert_not_called,
    make_dead_path,
    make_settings,
    no_close,
)

DEFAULT_USER_ID = "default-user-id-test"

DEFAULT_STATS_THREAD_COUNT = 7


def noop_update_settings(
    settings: Settings, incomplete_settings: Mapping[str, object]
) -> tuple[Settings, bool]:
    return settings, False


def make_settings_dict(
    user_id: str | None = None,
    hypixel_api_key: str | None = None,
    antisniper_api_key: str | None = None,
    use_antisniper_api: bool | None = None,
    sort_order: ColumnName | None = None,
    column_order: tuple[ColumnName, ...] | None = None,
    rating_configs: RatingConfigCollectionDict | None = None,
    known_nicks: dict[str, NickValue] | None = None,
    autodenick_teammates: bool | None = None,
    autoselect_logfile: bool | None = None,
    autohide_timeout: int | None = None,
    show_on_tab: bool | None = None,
    show_on_tab_keybind: KeyDict | None = None,
    autowho: bool | None = None,
    autowho_delay: float | None = None,
    chat_hotkey: KeyDict | None = None,
    activate_in_bedwars_duels: bool | None = None,
    check_for_updates: bool | None = None,
    include_patch_updates: bool | None = None,
    use_included_certs: bool | None = None,
    stats_thread_count: int | None = None,
    discord_rich_presence: bool | None = None,
    discord_show_username: bool | None = None,
    discord_show_session_stats: bool | None = None,
    discord_show_party: bool | None = None,
    hide_dead_players: bool | None = None,
    disable_overrideredirect: bool | None = None,
    hide_with_alpha: bool | None = None,
    alpha_hundredths: int | None = None,
) -> SettingsDict:
    """Make a settings dict with default values if missing"""
    return {
        "user_id": value_or_default(user_id, default=DEFAULT_USER_ID),
        "hypixel_api_key": value_or_default(hypixel_api_key, default=None),
        "antisniper_api_key": value_or_default(antisniper_api_key, default=None),
        "use_antisniper_api": value_or_default(use_antisniper_api, default=True),
        "sort_order": value_or_default(sort_order, default="index"),
        "column_order": value_or_default(
            column_order,
            default=("username", "stars", "fkdr", "kdr", "winstreak", "sessiontime"),
        ),
        "rating_configs": value_or_default(
            rating_configs, default=DEFAULT_RATING_CONFIG_COLLECTION_DICT
        ),
        "known_nicks": value_or_default(known_nicks, default={}),
        "autodenick_teammates": value_or_default(autodenick_teammates, default=True),
        "autoselect_logfile": value_or_default(autoselect_logfile, default=True),
        "autohide_timeout": value_or_default(autohide_timeout, default=8),
        "show_on_tab": value_or_default(show_on_tab, default=True),
        # mypy thinks this is {"name": str}, when it really is just KeyDict
        "show_on_tab_keybind": value_or_default(  # type: ignore [typeddict-item]
            show_on_tab_keybind,
            default=SpecialKeyDict(name="tab", vk=None, key_type="special"),
        ),
        "autowho": value_or_default(autowho, default=True),
        "autowho_delay": value_or_default(autowho_delay, default=2.0),
        # mypy thinks this is {"name": str}, when it really is just KeyDict
        "chat_hotkey": value_or_default(  # type: ignore [typeddict-item]
            chat_hotkey,
            default=AlphanumericKeyDict(name="t", char="t", key_type="alphanumeric"),
        ),
        "activate_in_bedwars_duels": value_or_default(
            activate_in_bedwars_duels, default=False
        ),
        "check_for_updates": value_or_default(check_for_updates, default=True),
        "include_patch_updates": value_or_default(include_patch_updates, default=False),
        "use_included_certs": value_or_default(use_included_certs, default=True),
        "stats_thread_count": value_or_default(
            stats_thread_count, default=DEFAULT_STATS_THREAD_COUNT
        ),
        "discord_rich_presence": value_or_default(discord_rich_presence, default=True),
        "discord_show_username": value_or_default(discord_show_username, default=True),
        "discord_show_session_stats": value_or_default(
            discord_show_session_stats, default=True
        ),
        "discord_show_party": value_or_default(discord_show_party, default=False),
        "hide_dead_players": value_or_default(hide_dead_players, default=True),
        "disable_overrideredirect": value_or_default(
            disable_overrideredirect, default=False
        ),
        "hide_with_alpha": value_or_default(hide_with_alpha, default=False),
        "alpha_hundredths": value_or_default(alpha_hundredths, default=80),
    }


PLACEHOLDER_PATH = make_dead_path("PLACEHOLDER_PATH")

settings_to_dict_cases: tuple[tuple[Settings, SettingsDict], ...] = (
    (
        Settings(
            user_id="my-user-id",
            hypixel_api_key="my-key",
            antisniper_api_key="my-key",
            use_antisniper_api=True,
            sort_order="stars",
            column_order=("username", "winstreak", "stars"),
            rating_configs=DEFAULT_RATING_CONFIG_COLLECTION,
            known_nicks={"AmazingNick": {"uuid": "123987", "comment": "Player1"}},
            autodenick_teammates=True,
            autoselect_logfile=True,
            autohide_timeout=8,
            show_on_tab=True,
            show_on_tab_keybind=AlphanumericKey(name="a", char="a"),
            autowho=True,
            autowho_delay=2.1,
            chat_hotkey=AlphanumericKey(name="u", char="u"),
            activate_in_bedwars_duels=False,
            check_for_updates=True,
            include_patch_updates=False,
            use_included_certs=False,
            stats_thread_count=4,
            discord_rich_presence=True,
            discord_show_username=True,
            discord_show_session_stats=True,
            discord_show_party=False,
            hide_dead_players=True,
            disable_overrideredirect=True,
            hide_with_alpha=True,
            alpha_hundredths=80,
            write_settings_file_utf8=lambda: io.StringIO(),
        ),
        {
            "user_id": "my-user-id",
            "hypixel_api_key": "my-key",
            "antisniper_api_key": "my-key",
            "use_antisniper_api": True,
            "sort_order": "stars",
            "column_order": ("username", "winstreak", "stars"),
            "rating_configs": DEFAULT_RATING_CONFIG_COLLECTION_DICT,
            "known_nicks": {"AmazingNick": {"uuid": "123987", "comment": "Player1"}},
            "autodenick_teammates": True,
            "autoselect_logfile": True,
            "autohide_timeout": 8,
            "show_on_tab": True,
            "show_on_tab_keybind": AlphanumericKeyDict(
                name="a", char="a", key_type="alphanumeric"
            ),
            "autowho": True,
            "autowho_delay": 2.1,
            "chat_hotkey": AlphanumericKeyDict(
                name="u", char="u", key_type="alphanumeric"
            ),
            "activate_in_bedwars_duels": False,
            "check_for_updates": True,
            "include_patch_updates": False,
            "use_included_certs": False,
            "stats_thread_count": 4,
            "discord_rich_presence": True,
            "discord_show_username": True,
            "discord_show_session_stats": True,
            "discord_show_party": False,
            "hide_dead_players": True,
            "disable_overrideredirect": True,
            "hide_with_alpha": True,
            "alpha_hundredths": 80,
        },
    ),
    (
        Settings(
            user_id="my-user-id-2",
            hypixel_api_key=None,
            antisniper_api_key="my-other-key",
            use_antisniper_api=False,
            sort_order="fkdr",
            column_order=("username", "stars", "fkdr", "wlr", "winstreak"),
            rating_configs=CUSTOM_RATING_CONFIG_COLLECTION,
            known_nicks={},
            autodenick_teammates=False,
            autoselect_logfile=False,
            autohide_timeout=19,
            show_on_tab=False,
            show_on_tab_keybind=SpecialKey(name="tab", vk=None),
            autowho=False,
            autowho_delay=0.1,
            chat_hotkey=AlphanumericKey(name="x", char="x"),
            activate_in_bedwars_duels=True,
            check_for_updates=False,
            include_patch_updates=True,
            use_included_certs=True,
            stats_thread_count=16,
            discord_rich_presence=False,
            discord_show_username=False,
            discord_show_session_stats=False,
            discord_show_party=True,
            hide_dead_players=False,
            disable_overrideredirect=False,
            hide_with_alpha=False,
            alpha_hundredths=30,
            write_settings_file_utf8=lambda: io.StringIO(),
        ),
        {
            "user_id": "my-user-id-2",
            "hypixel_api_key": None,
            "antisniper_api_key": "my-other-key",
            "use_antisniper_api": False,
            "sort_order": "fkdr",
            "column_order": ("username", "stars", "fkdr", "wlr", "winstreak"),
            "rating_configs": CUSTOM_RATING_CONFIG_COLLECTION_DICT,
            "known_nicks": {},
            "autodenick_teammates": False,
            "autoselect_logfile": False,
            "autohide_timeout": 19,
            "show_on_tab": False,
            "show_on_tab_keybind": SpecialKeyDict(
                name="tab", vk=None, key_type="special"
            ),
            "autowho": False,
            "autowho_delay": 0.1,
            "chat_hotkey": AlphanumericKeyDict(
                name="x", char="x", key_type="alphanumeric"
            ),
            "activate_in_bedwars_duels": True,
            "check_for_updates": False,
            "include_patch_updates": True,
            "use_included_certs": True,
            "stats_thread_count": 16,
            "discord_rich_presence": False,
            "discord_show_username": False,
            "discord_show_session_stats": False,
            "discord_show_party": True,
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
    assert (
        Settings.from_dict(
            settings_dict, write_settings_file_utf8=lambda: io.StringIO()
        )
        == result
    )


@pytest.mark.parametrize(
    "settings_dict, result", tuple((t[1], t[0]) for t in settings_to_dict_cases)
)
def test_settings_update_from(settings_dict: SettingsDict, result: Settings) -> None:
    settings = Settings.from_dict(
        make_settings_dict(), write_settings_file_utf8=lambda: io.StringIO()
    )
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
    settings: Settings, settings_dict: SettingsDict
) -> None:
    file = no_close(io.StringIO())

    # Make a copy so we can mutate it
    settings = dataclasses.replace(settings)

    settings.write_settings_file_utf8 = lambda: file

    settings.flush_to_disk()

    def dont_write_file() -> TextIO:
        assert False, "Should not be called"

    # NOTE: We can no longer do this since we store some null values in the dictionary
    #       which just get stored as missing keys in the toml
    # read_settings_dict = read_settings(settings.path)
    # assert read_settings_dict == settings_dict

    assert (
        get_settings(
            read_settings_file_utf8=lambda: io.StringIO(file.getvalue()),
            write_settings_file_utf8=dont_write_file,
            default_stats_thread_count=DEFAULT_STATS_THREAD_COUNT,
            update_settings=noop_update_settings,
        )
        == settings
    )


def test_read_missing_settings_file(tmp_path: Path) -> None:
    # Assert that get_settings doesn't fail when file doesn't exist
    empty_path = tmp_path / "settings2.toml"

    @dataclasses.dataclass(frozen=True)
    class FakeUUID:
        hex: str

    with mock.patch(
        "prism.overlay.settings.uuid.uuid4",
        return_value=FakeUUID(hex=DEFAULT_USER_ID),
    ):
        assert get_settings(
            read_settings_file_utf8=lambda: open(empty_path, "r", encoding="utf-8"),
            write_settings_file_utf8=lambda: open(empty_path, "w", encoding="utf-8"),
            default_stats_thread_count=DEFAULT_STATS_THREAD_COUNT,
            update_settings=noop_update_settings,
        ) == Settings.from_dict(
            source=make_settings_dict(), write_settings_file_utf8=lambda: io.StringIO()
        )


def test_read_settings_file_error() -> None:
    # Assert that get_settings doesn't fail when reading the file fails
    def read_settings_file_utf8() -> TextIO:
        raise IOError("Failed to read file")

    write_settings_called = False

    def write_settings_file_utf8() -> TextIO:
        nonlocal write_settings_called
        write_settings_called = True

        return io.StringIO()

    @dataclasses.dataclass(frozen=True)
    class FakeUUID:
        hex: str

    with mock.patch(
        "prism.overlay.settings.uuid.uuid4",
        return_value=FakeUUID(hex=DEFAULT_USER_ID),
    ):
        assert get_settings(
            read_settings_file_utf8=read_settings_file_utf8,
            write_settings_file_utf8=write_settings_file_utf8,
            default_stats_thread_count=DEFAULT_STATS_THREAD_COUNT,
            update_settings=noop_update_settings,
        ) == Settings.from_dict(
            source=make_settings_dict(), write_settings_file_utf8=lambda: io.StringIO()
        )

    assert write_settings_called


def test_flush_settings_from_controller() -> None:
    from prism.overlay.nick_database import NickDatabase
    from prism.overlay.real_controller import RealOverlayController
    from tests.prism.overlay.utils import (
        create_state,
    )

    file = no_close(io.StringIO())

    settings = make_settings(write_settings_file_utf8=lambda: file)

    # File not found
    assert (
        get_settings(
            read_settings_file_utf8=lambda: io.StringIO(""),
            write_settings_file_utf8=lambda: io.StringIO(),
            default_stats_thread_count=DEFAULT_STATS_THREAD_COUNT,
            update_settings=noop_update_settings,
        )
        != settings
    )

    controller = RealOverlayController(
        state=create_state(),
        settings=settings,
        nick_database=NickDatabase([{}]),
        get_uuid=assert_not_called,
        get_playerdata=assert_not_called,
        get_estimated_winstreaks=assert_not_called,
    )

    controller.store_settings()

    # File properly stored
    assert (
        get_settings(
            read_settings_file_utf8=lambda: io.StringIO(file.getvalue()),
            write_settings_file_utf8=lambda: io.StringIO(),
            default_stats_thread_count=DEFAULT_STATS_THREAD_COUNT,
            update_settings=noop_update_settings,
        )
        == settings
    )


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


fill_settings_test_cases: tuple[
    tuple[Mapping[str, object], SettingsDict, bool], ...
] = (
    (
        {"user_id": "my-user-id-3"},
        make_settings_dict(user_id="my-user-id-3"),
        True,
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
        {
            "user_id": "my-user-id-4",
            "antisniper_api_key": "my-key",
            "use_antisniper_api": False,
            "sort_order": "winstreak",
            "column_order": ("username", "stars", "fkdr", "wlr"),
            "rating_configs": CUSTOM_RATING_CONFIG_COLLECTION_DICT,
            "known_nicks": {"AmazingNick": {"uuid": "123987", "comment": "Player1"}},
            "autodenick_teammates": False,
            "autoselect_logfile": False,
            "autohide_timeout": 3,
            "show_on_tab": False,
            "show_on_tab_keybind": SpecialKeyDict(
                name="somekey", vk=123456, key_type="special"
            ),
            "autowho": True,
            "autowho_delay": 1,
            "chat_hotkey": SpecialKeyDict(
                name="somekey", vk=1234567, key_type="special"
            ),
            "activate_in_bedwars_duels": True,
            "check_for_updates": False,
            "include_patch_updates": True,
            "use_included_certs": True,
            "stats_thread_count": 9,
            "discord_rich_presence": False,
            "discord_show_username": False,
            "discord_show_session_stats": False,
            "discord_show_party": True,
            "hide_dead_players": False,
            "disable_overrideredirect": True,
            "hide_with_alpha": True,
            "alpha_hundredths": 40,
        },
        make_settings_dict(
            user_id="my-user-id-4",
            antisniper_api_key="my-key",
            use_antisniper_api=False,
            sort_order="winstreak",
            column_order=("username", "stars", "fkdr", "wlr"),
            rating_configs=CUSTOM_RATING_CONFIG_COLLECTION_DICT,
            known_nicks={"AmazingNick": {"uuid": "123987", "comment": "Player1"}},
            autodenick_teammates=False,
            autoselect_logfile=False,
            autohide_timeout=3,
            show_on_tab=False,
            show_on_tab_keybind=SpecialKeyDict(
                name="somekey", vk=123456, key_type="special"
            ),
            autowho=True,
            autowho_delay=1,
            chat_hotkey=SpecialKeyDict(name="somekey", vk=1234567, key_type="special"),
            activate_in_bedwars_duels=True,
            check_for_updates=False,
            include_patch_updates=True,
            use_included_certs=True,
            stats_thread_count=9,
            discord_rich_presence=False,
            discord_show_username=False,
            discord_show_session_stats=False,
            discord_show_party=True,
            hide_dead_players=False,
            disable_overrideredirect=True,
            hide_with_alpha=True,
            alpha_hundredths=40,
        ),
        False,
    ),
    (
        {"antisniper_api_key": "my-key"},
        make_settings_dict(antisniper_api_key="my-key"),
        True,
    ),
    (
        {"antisniper_api_key": 1},
        make_settings_dict(),
        True,
    ),
    (
        {"antisniper_api_key": None},
        make_settings_dict(),
        True,
    ),
    (
        {
            "antisniper_api_key": {},
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
        {"antisniper_api_key": "my-key", "use_antisniper_api": True},
        make_settings_dict(antisniper_api_key="my-key", use_antisniper_api=True),
        True,
    ),
    # Placeholder key
    (
        {"antisniper_api_key": PLACEHOLDER_API_KEY},
        make_settings_dict(),
        True,
    ),
    # Key too short
    (
        {"antisniper_api_key": "k"},
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
            "antisniper_api_key": "my-key",
            "known_nicks": {
                # Key is not a string
                1234: {"uuid": 123987, "comment": "Player1"}
            },
        },
        make_settings_dict(antisniper_api_key="my-key"),
        True,
    ),
    (
        {
            "antisniper_api_key": "my-key",
            "known_nicks": {
                # Value is a string, not a dict
                "AmazingNick": "uuid",
            },
        },
        make_settings_dict(antisniper_api_key="my-key"),
        True,
    ),
    (
        {
            "antisniper_api_key": "my-key",
            "known_nicks": {
                # Incorrect type on uuid or comment
                "AmazingNick": {"uuid": 123987, "comment": "Player1"}
            },
        },
        make_settings_dict(antisniper_api_key="my-key"),
        True,
    ),
    (
        {
            "antisniper_api_key": "my-key",
            "known_nicks": {
                # Incorrect type on uuid or comment
                "AmazingNick": {"uuid": "123987", "comment": 1234}
            },
        },
        make_settings_dict(antisniper_api_key="my-key"),
        True,
    ),
    (
        {
            "antisniper_api_key": "my-key",
            # Alpha hundredths out of range
            "alpha_hundredths": 1000,
        },
        make_settings_dict(antisniper_api_key="my-key"),
        True,
    ),
    (
        {
            "antisniper_api_key": "my-key",
            # Alpha hundredths out of range
            "alpha_hundredths": 5,
        },
        make_settings_dict(antisniper_api_key="my-key"),
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
    # Invalid sort orders
    (
        {"sort_order": ""},
        make_settings_dict(),
        True,
    ),
    (
        {"sort_order": "sort_by_winstreak_please"},
        make_settings_dict(),
        True,
    ),
    (
        {"sort_order": None},
        make_settings_dict(),
        True,
    ),
    (
        {"sort_order": []},
        make_settings_dict(),
        True,
    ),
    # Invalid stats_thread_count
    (
        {"stats_thread_count": []},
        make_settings_dict(),
        True,
    ),
    (
        {"stats_thread_count": "lkJ"},
        make_settings_dict(),
        True,
    ),
    (
        {"stats_thread_count": 0},
        make_settings_dict(),
        True,
    ),
    (
        {"stats_thread_count": 17},
        make_settings_dict(),
        True,
    ),
    # Valid stats_thread_count
    (
        {"stats_thread_count": 1},
        make_settings_dict(stats_thread_count=1),
        True,
    ),
    (
        {"stats_thread_count": 16},
        make_settings_dict(stats_thread_count=16),
        True,
    ),
    # Invalid discord settings
    (
        {
            "discord_rich_presence": [],
            "discord_show_username": (),
            "discord_show_session_stats": 0,
            "discord_show_party": 1e3,
        },
        make_settings_dict(),
        True,
    ),
    # Invalid use_included_certs
    (
        {
            "use_included_certs": ("", ""),
        },
        make_settings_dict(),
        True,
    ),
    (
        {
            "use_included_certs": [1],
        },
        make_settings_dict(),
        True,
    ),
    (
        {
            "use_included_certs": 1,
        },
        make_settings_dict(),
        True,
    ),
    (
        {"autohide_timeout": 13},
        make_settings_dict(autohide_timeout=13),
        True,
    ),
    (
        # Invalid data for autohide_timeout
        {"autohide_timeout": "yes"},
        make_settings_dict(),
        True,
    ),
    (
        # Invalid data for autohide_timeout
        {"autohide_timeout": 123456789},
        make_settings_dict(),
        True,
    ),
    (
        # Invalid data for autowho
        {"autowho": 123456789},
        make_settings_dict(),
        True,
    ),
    # Invalid data for autowho_delay
    (
        # Out of range
        {"autowho_delay": 123456789},
        make_settings_dict(),
        True,
    ),
    (
        # Out of range
        {"autowho_delay": 0.0},
        make_settings_dict(),
        True,
    ),
    (
        # Invalid type
        {"autowho_delay": "2.0"},
        make_settings_dict(),
        True,
    ),
    (
        # Out of range
        {"autowho_delay": 6},
        make_settings_dict(),
        True,
    ),
    (
        # Invalid type for chat_hotkey
        {"chat_hotkey": 5},
        make_settings_dict(),
        True,
    ),
    (
        # Invalid key type for chat_hotkey
        {
            "chat_hotkey": {
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
        {"chat_hotkey": {"key_type": "special", "vk": "badvk", "name": "name"}},
        make_settings_dict(),
        True,
    ),
    (
        # Invalid data for alphanumeric key
        {
            "chat_hotkey": {
                "key_type": "alphanumeric",
                "char": 1234,
                "name": "name",
            }
        },
        make_settings_dict(),
        True,
    ),
)


@pytest.mark.parametrize(
    "incomplete_settings, result_dict, result_updated", fill_settings_test_cases
)
def test_fill_missing_settings(
    incomplete_settings: Mapping[str, object],
    result_dict: SettingsDict,
    result_updated: bool,
) -> None:
    @dataclasses.dataclass(frozen=True)
    class FakeUUID:
        hex: str

    with mock.patch(
        "prism.overlay.settings.uuid.uuid4",
        return_value=FakeUUID(hex=DEFAULT_USER_ID),
    ):
        settings_dict, settings_updated = fill_missing_settings(
            incomplete_settings, DEFAULT_STATS_THREAD_COUNT
        )
    assert settings_dict == result_dict
    assert settings_updated == result_updated


def test_sort_ascending() -> None:
    settings = Settings.from_dict(
        make_settings_dict(
            sort_order="stars", rating_configs=CUSTOM_RATING_CONFIG_COLLECTION_DICT
        ),
        write_settings_file_utf8=lambda: io.StringIO(),
    )

    assert settings.sort_ascending

    settings.sort_order = "index"
    assert not settings.sort_ascending

    settings.sort_order = "username"
    assert not settings.sort_ascending


def test_update_settings() -> None:
    def update_settings(
        settings: Settings, incomplete_settings: Mapping[str, object]
    ) -> tuple[Settings, bool]:
        assert incomplete_settings == {}
        settings.autowho = False
        settings.hide_dead_players = False
        settings.user_id = "new-user-id"
        settings.antisniper_api_key = "updated-antisniper-key"
        return settings, True

    target_settings = Settings.from_dict(
        source=make_settings_dict(
            autowho=False,
            hide_dead_players=False,
            user_id="new-user-id",
            antisniper_api_key="updated-antisniper-key",
        ),
        write_settings_file_utf8=lambda: io.StringIO(),
    )

    file = no_close(io.StringIO())

    assert (
        get_settings(
            read_settings_file_utf8=lambda: io.StringIO(""),  # Empty file to start
            write_settings_file_utf8=lambda: file,  # Capture writes to this file
            default_stats_thread_count=DEFAULT_STATS_THREAD_COUNT,
            update_settings=update_settings,
        )
        == target_settings
    ), "Get with updates should return updated settings"

    assert (
        get_settings(
            read_settings_file_utf8=lambda: io.StringIO(file.getvalue()),
            write_settings_file_utf8=lambda: io.StringIO(),  # Should not be called
            default_stats_thread_count=DEFAULT_STATS_THREAD_COUNT,
            update_settings=noop_update_settings,
        )
        == target_settings
    ), "Updated settings should have been persisted in last call"
