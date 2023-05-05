from dataclasses import dataclass
from typing import Literal, Self, TypeGuard

ColumnName = Literal["username", "stars", "fkdr", "wlr", "winstreak"]

ALL_COLUMN_NAMES: frozenset[ColumnName] = frozenset(
    ("username", "stars", "fkdr", "wlr", "winstreak")
)

DEFAULT_COLUMN_ORDER: tuple[ColumnName, ...] = (
    "username",
    "stars",
    "fkdr",
    "winstreak",
)

COLUMN_NAMES: dict[ColumnName, str] = {
    "username": "IGN (Nick)",
    "stars": "Stars",
    "fkdr": "FKDR",
    "wlr": "WLR",
    "winstreak": "WS",
}


def str_is_column_name(column_name: str, /) -> TypeGuard[ColumnName]:
    """Typeguard for str -> ColumnName checks"""
    return column_name in ALL_COLUMN_NAMES


def object_is_column_name(column_name: object, /) -> TypeGuard[ColumnName]:
    """Typeguard for object -> ColumnName checks"""
    return isinstance(column_name, str) and str_is_column_name(column_name)


@dataclass(frozen=True, slots=True)
class ColorSection:
    """The color and length of the colored region, -1 if unlimited"""

    color: str  # Hex value, including the #
    length: int


@dataclass(frozen=True, slots=True)
class CellValue:
    """The string value and colors for a single cell in the overlay"""

    text: str
    terminal_formatting: str
    color_sections: tuple[ColorSection, ...]

    @classmethod
    def monochrome(cls, text: str, terminal_formatting: str, gui_color: str) -> Self:
        """Make a monochrome cell value"""
        return cls(
            text,
            terminal_formatting=terminal_formatting,
            color_sections=(ColorSection(gui_color, -1),),
        )


@dataclass(frozen=True, slots=True)
class InfoCellValue:
    """A value that can be set to an info-cell"""

    text: str
    color: str
    url: str | None
