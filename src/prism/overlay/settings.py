import logging
import threading
import uuid
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self, TypedDict, TypeVar

import toml

from prism.overlay.keybinds import (
    Key,
    KeyDict,
    SpecialKeyDict,
    construct_key,
    construct_key_dict,
)
from prism.overlay.output.cells import (
    DEFAULT_COLUMN_ORDER,
    ColumnName,
    object_is_column_name,
)
from prism.overlay.output.config import (
    RatingConfigCollection,
    RatingConfigCollectionDict,
    safe_read_rating_config_collection_dict,
)

PLACEHOLDER_API_KEY = "insert-your-key-here"


logger = logging.getLogger(__name__)


class NickValue(TypedDict):
    """Value for a key in known_nicks"""

    uuid: str
    comment: str  # Usually the original ign


class SettingsDict(TypedDict):
    """Complete dict of settings"""

    user_id: str
    hypixel_api_key: str | None
    antisniper_api_key: str | None
    use_antisniper_api: bool
    sort_order: ColumnName
    column_order: tuple[ColumnName, ...]
    rating_configs: RatingConfigCollectionDict
    known_nicks: dict[str, NickValue]
    autodenick_teammates: bool
    autoselect_logfile: bool
    show_on_tab: bool
    show_on_tab_keybind: KeyDict
    check_for_updates: bool
    include_patch_updates: bool
    stats_thread_count: int
    discord_rich_presence: bool
    discord_show_username: bool
    discord_show_session_stats: bool
    discord_show_party: bool
    hide_dead_players: bool
    disable_overrideredirect: bool
    hide_with_alpha: bool
    alpha_hundredths: int


@dataclass
class Settings:
    """Class holding user settings for the application"""

    user_id: str
    hypixel_api_key: str | None
    antisniper_api_key: str | None
    use_antisniper_api: bool
    sort_order: ColumnName
    column_order: tuple[ColumnName, ...]
    rating_configs: RatingConfigCollection
    known_nicks: dict[str, NickValue]
    autodenick_teammates: bool
    autoselect_logfile: bool
    show_on_tab: bool
    show_on_tab_keybind: Key
    check_for_updates: bool
    include_patch_updates: bool
    stats_thread_count: int
    discord_rich_presence: bool
    discord_show_username: bool
    discord_show_session_stats: bool
    discord_show_party: bool
    hide_dead_players: bool
    disable_overrideredirect: bool
    hide_with_alpha: bool
    alpha_hundredths: int
    path: Path
    mutex: threading.Lock = field(
        default_factory=threading.Lock, init=False, compare=False, repr=False
    )

    @property
    def sort_ascending(self) -> bool:
        """Return True if the sort order is ascending for the current sort column"""
        sort_order = self.sort_order  # The column we sort on
        if sort_order == "username":
            return False

        config = self.rating_configs.to_dict()[sort_order]

        return config["sort_ascending"]

    @classmethod
    def from_dict(cls, source: SettingsDict, path: Path) -> Self:
        return cls(
            user_id=source["user_id"],
            hypixel_api_key=source["hypixel_api_key"],
            antisniper_api_key=source["antisniper_api_key"],
            use_antisniper_api=source["use_antisniper_api"],
            sort_order=source["sort_order"],
            column_order=source["column_order"],
            rating_configs=RatingConfigCollection.from_dict(source["rating_configs"]),
            known_nicks=source["known_nicks"],
            autodenick_teammates=source["autodenick_teammates"],
            autoselect_logfile=source["autoselect_logfile"],
            show_on_tab=source["show_on_tab"],
            show_on_tab_keybind=construct_key(source["show_on_tab_keybind"]),
            check_for_updates=source["check_for_updates"],
            include_patch_updates=source["include_patch_updates"],
            stats_thread_count=source["stats_thread_count"],
            discord_rich_presence=source["discord_rich_presence"],
            discord_show_username=source["discord_show_username"],
            discord_show_session_stats=source["discord_show_session_stats"],
            discord_show_party=source["discord_show_party"],
            hide_dead_players=source["hide_dead_players"],
            disable_overrideredirect=source["disable_overrideredirect"],
            hide_with_alpha=source["hide_with_alpha"],
            alpha_hundredths=source["alpha_hundredths"],
            path=path,
        )

    def to_dict(self) -> SettingsDict:
        return {
            "user_id": self.user_id,
            "hypixel_api_key": self.hypixel_api_key,
            "antisniper_api_key": self.antisniper_api_key,
            "use_antisniper_api": self.use_antisniper_api,
            "sort_order": self.sort_order,
            "column_order": self.column_order,
            "rating_configs": self.rating_configs.to_dict(),
            "known_nicks": self.known_nicks,
            "autodenick_teammates": self.autodenick_teammates,
            "autoselect_logfile": self.autoselect_logfile,
            "show_on_tab": self.show_on_tab,
            "show_on_tab_keybind": self.show_on_tab_keybind.to_dict(),
            "check_for_updates": self.check_for_updates,
            "include_patch_updates": self.include_patch_updates,
            "stats_thread_count": self.stats_thread_count,
            "discord_rich_presence": self.discord_rich_presence,
            "discord_show_username": self.discord_show_username,
            "discord_show_session_stats": self.discord_show_session_stats,
            "discord_show_party": self.discord_show_party,
            "hide_dead_players": self.hide_dead_players,
            "disable_overrideredirect": self.disable_overrideredirect,
            "hide_with_alpha": self.hide_with_alpha,
            "alpha_hundredths": self.alpha_hundredths,
        }

    def update_from(self, new_settings: SettingsDict) -> None:
        """Update the settings from the settings dict"""
        self.user_id = new_settings["user_id"]
        self.hypixel_api_key = new_settings["hypixel_api_key"]
        self.antisniper_api_key = new_settings["antisniper_api_key"]
        self.use_antisniper_api = new_settings["use_antisniper_api"]
        self.sort_order = new_settings["sort_order"]
        self.column_order = new_settings["column_order"]
        self.rating_configs = RatingConfigCollection.from_dict(
            new_settings["rating_configs"]
        )
        self.known_nicks = new_settings["known_nicks"]
        self.autodenick_teammates = new_settings["autodenick_teammates"]
        self.autoselect_logfile = new_settings["autoselect_logfile"]
        self.show_on_tab = new_settings["show_on_tab"]
        self.show_on_tab_keybind = construct_key(new_settings["show_on_tab_keybind"])
        self.check_for_updates = new_settings["check_for_updates"]
        self.include_patch_updates = new_settings["include_patch_updates"]
        self.stats_thread_count = new_settings["stats_thread_count"]
        self.discord_rich_presence = new_settings["discord_rich_presence"]
        self.discord_show_username = new_settings["discord_show_username"]
        self.discord_show_session_stats = new_settings["discord_show_session_stats"]
        self.discord_show_party = new_settings["discord_show_party"]
        self.hide_dead_players = new_settings["hide_dead_players"]
        self.disable_overrideredirect = new_settings["disable_overrideredirect"]
        self.hide_with_alpha = new_settings["hide_with_alpha"]
        self.alpha_hundredths = new_settings["alpha_hundredths"]

    def flush_to_disk(self) -> None:
        # toml.load(path) uses encoding='utf-8'
        with self.path.open("w", encoding="utf-8") as f:
            toml.dump(self.to_dict(), f)
        logger.info(f"Wrote settings to disk: {self}")


# Generic type for value_or_default
ValueType = TypeVar("ValueType")


def value_or_default(value: ValueType | None, *, default: ValueType) -> ValueType:
    return value if value is not None else default


def api_key_is_valid(key: str) -> bool:
    """Return True if given key is a valid API key"""
    # Very permissive validity checks - no guarantee for validity
    return key != PLACEHOLDER_API_KEY and len(key) > 5


def read_settings(path: Path) -> MutableMapping[str, object]:
    return toml.load(path)


def get_boolean_setting(
    incomplete_settings: Mapping[str, object],
    key: str,
    settings_updated: bool,
    *,
    default: bool,
) -> tuple[bool, bool]:
    """Return value, settings_updated"""
    value = incomplete_settings.get(key, None)

    if not isinstance(value, bool):
        return default, True

    return value, settings_updated


def fill_missing_settings(
    incomplete_settings: Mapping[str, object],
    default_stats_thread_count: int,
) -> tuple[SettingsDict, bool]:
    """Get settings from `incomplete_settings` and fill with defaults if missing"""
    settings_updated = False

    user_id = incomplete_settings.get("user_id", None)
    if user_id is None or not isinstance(user_id, str):
        settings_updated = True
        user_id = uuid.uuid4().hex

    hypixel_api_key = incomplete_settings.get("hypixel_api_key", None)
    if hypixel_api_key is not None and (
        not isinstance(hypixel_api_key, str) or not api_key_is_valid(hypixel_api_key)
    ):
        settings_updated = True
        hypixel_api_key = None

    antisniper_api_key = incomplete_settings.get("antisniper_api_key", None)
    if not isinstance(antisniper_api_key, str) or not api_key_is_valid(
        antisniper_api_key
    ):
        settings_updated = True
        antisniper_api_key = None

    use_antisniper_api, settings_updated = get_boolean_setting(
        incomplete_settings, "use_antisniper_api", settings_updated, default=True
    )

    sort_order: ColumnName | object = incomplete_settings.get("sort_order", None)
    if not object_is_column_name(sort_order):
        sort_order = "index"
        settings_updated = True

    raw_column_order = incomplete_settings.get("column_order", None)
    if isinstance(raw_column_order, (list, tuple)):
        column_order = tuple(filter(object_is_column_name, raw_column_order))
        settings_updated |= len(raw_column_order) != len(column_order)
    else:
        # Found no columns
        column_order = ()

    # No valid column_names provided
    if not column_order:
        column_order = DEFAULT_COLUMN_ORDER
        settings_updated = True

    (
        rating_configs_dict,
        rating_configs_updated,
    ) = safe_read_rating_config_collection_dict(
        incomplete_settings.get("rating_configs", None)
    )
    settings_updated |= rating_configs_updated

    known_nicks_source = incomplete_settings.get("known_nicks", None)
    if not isinstance(known_nicks_source, dict):
        settings_updated = True
        known_nicks_source = {}

    known_nicks: dict[str, NickValue] = {}
    for key, value in known_nicks_source.items():
        if not isinstance(key, str):
            settings_updated = True
            continue

        if not isinstance(value, dict):
            settings_updated = True
            continue

        nick_uuid = value.get("uuid", None)
        comment = value.get("comment", None)

        if not isinstance(nick_uuid, str) or not isinstance(comment, str):
            settings_updated = True
            continue

        known_nicks[key] = NickValue(uuid=nick_uuid, comment=comment)

    autodenick_teammates, settings_updated = get_boolean_setting(
        incomplete_settings, "autodenick_teammates", settings_updated, default=True
    )

    autoselect_logfile, settings_updated = get_boolean_setting(
        incomplete_settings, "autoselect_logfile", settings_updated, default=True
    )

    show_on_tab, settings_updated = get_boolean_setting(
        incomplete_settings, "show_on_tab", settings_updated, default=True
    )

    show_on_tab_keybind: KeyDict
    sot_keybind_source = incomplete_settings.get("show_on_tab_keybind", None)
    if (
        # Invalid type
        not isinstance(sot_keybind_source, dict)
        # Failed parsing to key dict
        or (sot_keybind_key_dict := construct_key_dict(sot_keybind_source)) is None
    ):
        settings_updated = True
        # Special key with name tab and vk None is replaced with the real representation
        # for tab in the listener
        show_on_tab_keybind = SpecialKeyDict(name="tab", vk=None, key_type="special")
    else:
        show_on_tab_keybind = sot_keybind_key_dict

    check_for_updates, settings_updated = get_boolean_setting(
        incomplete_settings, "check_for_updates", settings_updated, default=True
    )

    include_patch_updates, settings_updated = get_boolean_setting(
        incomplete_settings, "include_patch_updates", settings_updated, default=False
    )

    stats_thread_count = incomplete_settings.get("stats_thread_count", None)
    if not isinstance(stats_thread_count, int) or not 1 <= stats_thread_count <= 16:
        settings_updated = True
        stats_thread_count = default_stats_thread_count

    discord_rich_presence, settings_updated = get_boolean_setting(
        incomplete_settings, "discord_rich_presence", settings_updated, default=True
    )

    discord_show_username, settings_updated = get_boolean_setting(
        incomplete_settings, "discord_show_username", settings_updated, default=True
    )

    discord_show_session_stats, settings_updated = get_boolean_setting(
        incomplete_settings,
        "discord_show_session_stats",
        settings_updated,
        default=True,
    )

    discord_show_party, settings_updated = get_boolean_setting(
        incomplete_settings, "discord_show_party", settings_updated, default=False
    )

    hide_dead_players, settings_updated = get_boolean_setting(
        incomplete_settings, "hide_dead_players", settings_updated, default=True
    )

    disable_overrideredirect, settings_updated = get_boolean_setting(
        incomplete_settings, "disable_overrideredirect", settings_updated, default=False
    )

    hide_with_alpha, settings_updated = get_boolean_setting(
        incomplete_settings, "hide_with_alpha", settings_updated, default=False
    )

    alpha_hundredths = incomplete_settings.get("alpha_hundredths", None)
    if not isinstance(alpha_hundredths, int) or not 10 <= alpha_hundredths <= 100:
        settings_updated = True
        alpha_hundredths = 80

    return {
        "user_id": user_id,
        "hypixel_api_key": hypixel_api_key,
        "antisniper_api_key": antisniper_api_key,
        "use_antisniper_api": use_antisniper_api,
        "sort_order": sort_order,
        "column_order": column_order,
        "rating_configs": rating_configs_dict,
        "known_nicks": known_nicks,
        "autodenick_teammates": autodenick_teammates,
        "autoselect_logfile": autoselect_logfile,
        "show_on_tab": show_on_tab,
        "show_on_tab_keybind": show_on_tab_keybind,
        "check_for_updates": check_for_updates,
        "include_patch_updates": include_patch_updates,
        "stats_thread_count": stats_thread_count,
        "discord_rich_presence": discord_rich_presence,
        "discord_show_username": discord_show_username,
        "discord_show_session_stats": discord_show_session_stats,
        "discord_show_party": discord_show_party,
        "hide_dead_players": hide_dead_players,
        "disable_overrideredirect": disable_overrideredirect,
        "hide_with_alpha": hide_with_alpha,
        "alpha_hundredths": alpha_hundredths,
    }, settings_updated


def get_settings(path: Path, default_stats_thread_count: int) -> Settings:
    """
    Read the stored settings into a Settings object

    Calls get_api_key if it is missing
    NOTE: Will write to the path if the API key is missing
    """
    try:
        incomplete_settings = read_settings(path)
    except Exception as e:
        # Error either in reading or parsing file
        incomplete_settings = {}
        logger.warning("Error reading settings file, using all defaults.", exc_info=e)

    settings_dict, settings_updated = fill_missing_settings(
        incomplete_settings, default_stats_thread_count
    )

    settings = Settings.from_dict(settings_dict, path=path)

    if settings_updated:
        settings.flush_to_disk()

    logger.info(f"Read settings from disk: {settings}")
    return settings
