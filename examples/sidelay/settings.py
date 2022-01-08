from dataclasses import dataclass
from pathlib import Path
from typing import Callable, MutableMapping, Optional, Type, TypedDict, TypeVar

import toml


class SettingsDict(TypedDict):
    """Complete dict of settings"""

    hypixel_api_key: str


# Generic type to allow subclassing Settings
DerivedSettings = TypeVar("DerivedSettings", bound="Settings")


@dataclass
class Settings:
    """Class holding user settings for the application"""

    hypixel_api_key: str

    @classmethod
    def from_dict(cls: Type[DerivedSettings], source: SettingsDict) -> DerivedSettings:
        return cls(hypixel_api_key=source["hypixel_api_key"])

    def to_dict(self) -> SettingsDict:
        return {"hypixel_api_key": self.hypixel_api_key}


# Generic type for value_or_default
ValueType = TypeVar("ValueType")


def value_or_default(value: Optional[ValueType], *, default: ValueType) -> ValueType:
    return value if value is not None else default


def read_settings(path: Path) -> MutableMapping[str, object]:
    return toml.load(path)


def fill_missing_settings(
    incomplete_settings: MutableMapping[str, object], get_api_key: Callable[[], str]
) -> SettingsDict:
    api_key = incomplete_settings.get("hypixel_api_key", None)
    if not isinstance(api_key, str):
        api_key = get_api_key()

    return {"hypixel_api_key": api_key}


def write_settings(settings: Settings, path: Path) -> None:
    settings_object = settings.to_dict()

    with path.open("w") as f:
        toml.dump(settings_object, f)


def get_settings(path: Path, get_api_key: Callable[[], str]) -> Settings:
    """
    Read the stored settings into a Settings object

    Calls get_api_key if it is missing
    """
    incomplete_settings = read_settings(path)
    settings_dict = fill_missing_settings(incomplete_settings, get_api_key)

    return Settings.from_dict(settings_dict)
