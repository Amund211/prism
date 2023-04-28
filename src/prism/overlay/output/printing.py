import os
from collections.abc import Set

from prism.overlay.output.cell_renderer import pick_columns, render_stats
from prism.overlay.output.cells import COLUMN_NAMES, ColumnName
from prism.overlay.output.color import TerminalColor
from prism.overlay.output.config import RatingConfigCollection
from prism.overlay.player import Player

# Column separator
SEP = " " * 4


def clear_screen() -> None:  # pragma: nocover
    """Blank the screen"""
    os.system("cls" if os.name == "nt" else "clear")


def title(text: str) -> str:
    """Format the given text like a title (in bold)"""
    return TerminalColor.BOLD + text + TerminalColor.END


def color(text: str, color: str) -> str:
    """Color the given text the given color"""
    return color + text + TerminalColor.END


def get_sep(column: str, column_order: tuple[ColumnName, ...]) -> str:
    """Get the separator used in prints for this column"""
    return "\n" if column == column_order[-1] else SEP


def print_stats_table(
    sorted_stats: list[Player],
    party_members: Set[str],
    column_order: tuple[ColumnName, ...],
    rating_configs: RatingConfigCollection,
    out_of_sync: bool,
    clear_between_draws: bool = True,
) -> None:  # pragma: nocover
    """Print the stats in a table format to stdout"""
    rows = tuple(
        pick_columns(render_stats(player, rating_configs), column_order)
        for player in sorted_stats
    )

    column_widths = tuple(
        len(
            max(
                (row[column_index].text for row in rows),
                default="",
                key=len,
            )
        )
        for column_index in range(len(column_order))
    )

    if clear_between_draws:
        clear_screen()

    if out_of_sync:
        print(
            title(
                TerminalColor.LIGHT_RED
                + TerminalColor.BG_WHITE
                + "The overlay is out of sync with the lobby. Please use /who."
            )
        )

    # Table header
    for i, column in enumerate(column_order):
        print(
            title(COLUMN_NAMES[column].ljust(column_widths[i])),
            end=get_sep(column, column_order),
        )

    for row in rows:
        for i, column in enumerate(column_order):
            # Left justify the first column
            justify = str.ljust if i == 0 else str.rjust

            cell_value = row[i]

            formatted_string = color(cell_value.text, cell_value.terminal_formatting)

            formatting_length = len(formatted_string) - len(cell_value.text)

            print(
                justify(formatted_string, column_widths[i] + formatting_length),
                end=get_sep(column, column_order),
            )
