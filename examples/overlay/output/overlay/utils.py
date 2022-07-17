import tkinter as tk
from dataclasses import dataclass
from typing import TypeVar

from examples.overlay.output.utils import STAT_LEVELS, rate_value
from examples.overlay.player import Player, PropertyName

ColumnKey = TypeVar("ColumnKey")


@dataclass
class Cell:
    """A cell in the window described by one label and one stringvar"""

    label: tk.Label
    variable: tk.StringVar


@dataclass(frozen=True)
class CellValue:
    """A value that can be set to a cell in the window"""

    text: str
    color: str


# One row in the overlay is a dict mapping column name to a cell value
OverlayRow = dict[ColumnKey, CellValue]


DEFAULT_COLOR = "snow"
LEVEL_COLORMAP = (
    "gray60",
    "snow",
    "yellow",
    "orange red",
    "red",
)

for levels in STAT_LEVELS.values():
    if levels is not None:
        assert len(levels) <= len(LEVEL_COLORMAP) - 1


def player_to_row(player: Player) -> OverlayRow[PropertyName]:
    """
    Create an OverlayRow from a Player instance

    Gets the text from player.get_string
    Gets the color by rating the stats
    """
    return {
        name: CellValue(
            text=player.get_string(name),
            color=(
                LEVEL_COLORMAP[rate_value(value, levels)]
                if levels is not None
                and isinstance(value := player.get_value(name), (int, float))
                else DEFAULT_COLOR
            ),
        )
        for name, levels in STAT_LEVELS.items()
    }
