from dataclasses import dataclass
from typing import Literal, Self, TypeGuard

GUI_COLORS = (
    "gray60",
    "snow",
    "yellow",
    "#FF8800",
    "red",
)

AMT_COLORS = len(GUI_COLORS)


ColumnName = Literal[
    "username",
    "stars",
    "index",
    "fkdr",
    "kdr",
    "bblr",
    "wlr",
    "winstreak",
    "kills",
    "finals",
    "beds",
    "wins",
    "sessiontime",
    "tags",
]

ALL_COLUMN_NAMES_ORDERED: tuple[ColumnName, ...] = (
    "username",
    "stars",
    "index",
    "fkdr",
    "kdr",
    "bblr",
    "wlr",
    "winstreak",
    "kills",
    "finals",
    "beds",
    "wins",
    "sessiontime",
    "tags",
)

ALL_COLUMN_NAMES: frozenset[ColumnName] = frozenset(ALL_COLUMN_NAMES_ORDERED)

DEFAULT_COLUMN_ORDER: tuple[ColumnName, ...] = (
    "username",
    "stars",
    "fkdr",
    "kdr",
    "winstreak",
    "sessiontime",
)

COLUMN_NAMES: dict[ColumnName, str] = {
    "username": "IGN (Nick)",
    "stars": "Stars",
    "index": "Index",
    "fkdr": "FKDR",
    "kdr": "KDR",
    "bblr": "BBLR",
    "wlr": "WLR",
    "winstreak": "WS",
    "kills": "Kills",
    "finals": "Finals",
    "beds": "Beds",
    "wins": "Wins",
    "sessiontime": "Time",
    "tags": "Tags",
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
    color_sections: tuple[ColorSection, ...]

    @classmethod
    def monochrome(cls, text: str, gui_color: str) -> Self:
        """Make a monochrome cell value"""
        return cls(
            text,
            color_sections=(ColorSection(gui_color, -1),),
        )

    @classmethod
    def pending(cls) -> Self:
        """Make a pending cell value"""
        return cls.monochrome("-", GUI_COLORS[0])

    @classmethod
    def error(cls) -> Self:
        """Make an error cell value"""
        return cls.monochrome("error", GUI_COLORS[-1])

    @classmethod
    def nicked(cls) -> Self:
        """Make a nicked cell value"""
        return cls.monochrome("nick", GUI_COLORS[-1])

    @classmethod
    def empty(cls) -> Self:
        """Make an empty cell value"""
        return cls.monochrome("", GUI_COLORS[0])


@dataclass(frozen=True, slots=True)
class InfoCellValue:
    """A value that can be set to an info-cell"""

    text: str
    color: str
    url: str | None
