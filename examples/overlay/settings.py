import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, MutableMapping, Type, TypedDict, TypeVar

import toml

PLACEHOLDER_API_KEY = "insert-your-key-here"


logger = logging.getLogger(__name__)


class NickValue(TypedDict):
    """Value for a key in known_nicks"""

    uuid: str
    comment: str  # Usually the original ign


class SettingsDict(TypedDict):
    """Complete dict of settings"""

    hypixel_api_key: str
    antisniper_api_key: str | None
    use_antisniper_api: bool
    known_nicks: dict[str, NickValue]


# Generic type to allow subclassing Settings
DerivedSettings = TypeVar("DerivedSettings", bound="Settings")


@dataclass
class Settings:
    """Class holding user settings for the application"""

    hypixel_api_key: str
    antisniper_api_key: str | None
    use_antisniper_api: bool
    known_nicks: dict[str, NickValue]
    path: Path
    mutex: threading.Lock = field(
        default_factory=threading.Lock, init=False, compare=False, repr=False
    )

    @classmethod
    def from_dict(
        cls: Type[DerivedSettings], source: SettingsDict, path: Path
    ) -> DerivedSettings:
        return cls(
            hypixel_api_key=source["hypixel_api_key"],
            antisniper_api_key=source["antisniper_api_key"],
            use_antisniper_api=source["use_antisniper_api"],
            known_nicks=source["known_nicks"],
            path=path,
        )

    def to_dict(self) -> SettingsDict:
        return {
            "hypixel_api_key": self.hypixel_api_key,
            "antisniper_api_key": self.antisniper_api_key,
            "use_antisniper_api": self.use_antisniper_api,
            "known_nicks": self.known_nicks,
        }

    def flush_to_disk(self) -> None:
        with self.path.open("w") as f:
            toml.dump(self.to_dict(), f)


# Generic type for value_or_default
ValueType = TypeVar("ValueType")


def value_or_default(value: ValueType | None, *, default: ValueType) -> ValueType:
    return value if value is not None else default


def api_key_is_valid(key: str) -> bool:
    """Return True if given key is a valid Hypixel API key"""
    # Very permissive validity checks - no guarantee for validity
    return key != PLACEHOLDER_API_KEY and len(key) > 5


def read_settings(path: Path) -> MutableMapping[str, object]:
    return toml.load(path)


def fill_missing_settings(
    incomplete_settings: MutableMapping[str, object], get_api_key: Callable[[], str]
) -> tuple[SettingsDict, bool]:
    """Get settings from `incomplete_settings` and fill with defaults if missing"""
    settings_updated = False

    hypixel_api_key = incomplete_settings.get("hypixel_api_key", None)
    if not isinstance(hypixel_api_key, str) or not api_key_is_valid(hypixel_api_key):
        settings_updated = True
        hypixel_api_key = get_api_key()

    antisniper_api_key = incomplete_settings.get("antisniper_api_key", None)
    if not isinstance(antisniper_api_key, str) or not api_key_is_valid(
        antisniper_api_key
    ):
        # Don't make any updates if the key is already set to the placeholder
        if antisniper_api_key != PLACEHOLDER_API_KEY:
            settings_updated = True
        antisniper_api_key = PLACEHOLDER_API_KEY

    use_antisniper_api = incomplete_settings.get("use_antisniper_api", None)
    if not isinstance(use_antisniper_api, bool):
        settings_updated = True
        use_antisniper_api = False

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

        uuid = value.get("uuid", None)
        comment = value.get("comment", None)

        if not isinstance(uuid, str) or not isinstance(comment, str):
            settings_updated = True
            continue

        known_nicks[key] = NickValue(uuid=uuid, comment=comment)

    return {
        "hypixel_api_key": hypixel_api_key,
        "antisniper_api_key": antisniper_api_key,
        "use_antisniper_api": use_antisniper_api,
        "known_nicks": known_nicks,
    }, settings_updated


def get_settings(path: Path, get_api_key: Callable[[], str]) -> Settings:
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
        logger.warning(f"Error reading settings file, using all defaults. '{e}'")

    if "hypixel_api_key" not in incomplete_settings:
        # To help users in setting a valid key, add a placeholder and flush to disk
        incomplete_settings["hypixel_api_key"] = PLACEHOLDER_API_KEY
        with path.open("w") as f:
            toml.dump(incomplete_settings, f)

    settings_dict, settings_updated = fill_missing_settings(
        incomplete_settings, get_api_key
    )

    settings = Settings.from_dict(settings_dict, path=path)

    if settings_updated:
        settings.flush_to_disk()

    return settings
