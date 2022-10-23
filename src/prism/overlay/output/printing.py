import os

from prism.overlay.output.utils import (
    COLUMN_NAMES,
    COLUMN_ORDER,
    STAT_LEVELS,
    rate_value,
)
from prism.overlay.player import Player


class Color:
    """
    SGR color constants
    rene-d 2018

    https://gist.github.com/rene-d/9e584a7dd2935d0f461904b9f2950007
    """

    BLACK = "\033[0;30m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    BROWN = "\033[0;33m"
    BLUE = "\033[0;34m"
    PURPLE = "\033[0;35m"
    CYAN = "\033[0;36m"
    LIGHT_GRAY = "\033[0;37m"
    DARK_GRAY = "\033[1;30m"
    LIGHT_RED = "\033[1;31m"
    LIGHT_GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    LIGHT_BLUE = "\033[1;34m"
    LIGHT_PURPLE = "\033[1;35m"
    LIGHT_CYAN = "\033[1;36m"
    LIGHT_WHITE = "\033[1;37m"

    BG_WHITE = "\033[47;1m"

    BOLD = "\033[1m"
    FAINT = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    NEGATIVE = "\033[7m"
    CROSSED = "\033[9m"
    END = "\033[0m"


# Column separator
SEP = " " * 4


LEVEL_COLORMAP = (
    Color.LIGHT_GRAY,
    Color.LIGHT_WHITE,
    Color.YELLOW,
    Color.LIGHT_RED,
    Color.LIGHT_RED + Color.BG_WHITE,
)

for levels in STAT_LEVELS.values():
    if levels is not None:
        assert len(levels) <= len(LEVEL_COLORMAP) - 1


def clear_screen() -> None:  # pragma: nocover
    """Blank the screen"""
    os.system("cls" if os.name == "nt" else "clear")


def title(text: str) -> str:
    """Format the given text like a title (in bold)"""
    return Color.BOLD + text + Color.END


def color(text: str, color: str) -> str:
    """Color the given text the given color"""
    return color + text + Color.END


def get_sep(column: str) -> str:
    """Get the separator used in prints for this column"""
    return "\n" if column == COLUMN_ORDER[-1] else SEP


def print_stats_table(
    sorted_stats: list[Player],
    party_members: set[str],
    out_of_sync: bool,
    clear_between_draws: bool = True,
) -> None:  # pragma: nocover
    """Print the stats in a table format to stdout"""
    column_widths = {
        column: len(
            max(
                (stat.get_string(column) for stat in sorted_stats),
                default="",
                key=len,
            )
        )
        for column in COLUMN_ORDER
    }

    if clear_between_draws:
        clear_screen()

    if out_of_sync:
        print(
            title(
                Color.LIGHT_RED
                + Color.BG_WHITE
                + "The overlay is out of sync with the lobby. Please use /who."
            )
        )

    # Table header
    for column in COLUMN_ORDER:
        print(
            title(COLUMN_NAMES[column].ljust(column_widths[column])),
            end=get_sep(column),
        )

    for stat in sorted_stats:
        for i, column in enumerate(COLUMN_ORDER):
            # Left justify the first column
            justify = str.ljust if i == 0 else str.rjust

            levels = STAT_LEVELS.get(column, None)

            stat_string = stat.get_string(column)
            stat_value = stat.get_value(column)

            if stat_value is None or levels is None or isinstance(stat_value, str):
                final_string = stat_string
            else:
                rating = rate_value(stat_value, levels)
                final_string = color(stat_string, LEVEL_COLORMAP[rating])

            print(
                justify(
                    final_string,
                    column_widths[column] + (len(final_string) - len(stat_string)),
                ),
                end=get_sep(column),
            )
