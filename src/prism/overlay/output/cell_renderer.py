from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import assert_never

from prism.overlay.output.cells import CellValue, ColorSection, ColumnName
from prism.overlay.output.color import GUIColor, MinecraftColor, TerminalColor
from prism.overlay.output.config import RatingConfigCollection
from prism.overlay.player import KnownPlayer, NickedPlayer, PendingPlayer, Player
from prism.utils import truncate_float

TERMINAL_FORMATTINGS = (
    TerminalColor.LIGHT_GRAY,
    TerminalColor.LIGHT_WHITE,
    TerminalColor.YELLOW,
    TerminalColor.LIGHT_RED,
    TerminalColor.LIGHT_RED + TerminalColor.BG_WHITE,
)

GUI_COLORS = (
    "gray60",
    "snow",
    "yellow",
    "#FF8800",
    "red",
)

AMT_LEVELS = len(GUI_COLORS)

assert len(TERMINAL_FORMATTINGS) == AMT_LEVELS


@dataclass(frozen=True, slots=True)
class RenderedStats:
    """Colored CellValues based on the rating for each stat"""

    username: CellValue
    stars: CellValue
    fkdr: CellValue
    wlr: CellValue
    winstreak: CellValue


def truncate_float_or_int(value: float | int, decimals: int) -> str:
    """Truncate the decimals of the float, or keep the int"""
    if isinstance(value, int):
        return str(value)
    return truncate_float(value, decimals)


def rate_value(value: float, levels: Sequence[float]) -> int:
    """
    Rate the value according to the provided levels (sorted)

    The rating is the smallest index i in levels that is such that
    value < levels[i]
    Alternatively the largest index i in levels such that
    value >= levels[i + 1]
    NOTE: If value >= levels[j] for all j, the rating will be `len(levels)`
    """
    for rating, level in enumerate(levels):
        if value < level:
            return rating

    # Passed all levels
    return rating + 1


def render_based_on_level(
    text: str, value: int | float, levels: tuple[float, ...]
) -> CellValue:
    rating = rate_value(value, levels)

    return CellValue.monochrome(
        text=text,
        terminal_formatting=TERMINAL_FORMATTINGS[rating],
        gui_color=GUI_COLORS[rating],
    )


def render_stars(stars: float, decimals: int, levels: tuple[float, ...]) -> CellValue:
    """
    Render the user's star using the Hypixel BedWars star colors

    Source (0-3000): https://hypixel.net/threads/tool-bedwars-prestige-colors-in-minecraft-color-code-and-hex-code-high-effort-post.3841719/  # noqa: E501
    """
    text = truncate_float(stars, decimals)

    color_sections: tuple[ColorSection, ...]
    prestige = int(stars // 100)
    if prestige == 0:
        color_sections = (ColorSection(MinecraftColor.GRAY, 1 if stars < 10 else 2),)
    elif prestige == 1:
        color_sections = (ColorSection(MinecraftColor.WHITE, 3),)
    elif prestige == 2:
        color_sections = (ColorSection(MinecraftColor.GOLD, 3),)
    elif prestige == 3:
        color_sections = (ColorSection(MinecraftColor.AQUA, 3),)
    elif prestige == 4:
        color_sections = (ColorSection(MinecraftColor.DARK_GREEN, 3),)
    elif prestige == 5:
        color_sections = (ColorSection(MinecraftColor.DARK_AQUA, 3),)
    elif prestige == 6:
        color_sections = (ColorSection(MinecraftColor.DARK_RED, 3),)
    elif prestige == 7:
        color_sections = (ColorSection(MinecraftColor.LIGHT_PURPLE, 3),)
    elif prestige == 8:
        color_sections = (ColorSection(MinecraftColor.BLUE, 3),)
    elif prestige == 9:
        color_sections = (ColorSection(MinecraftColor.DARK_PURPLE, 3),)
    elif prestige == 10:
        color_sections = (
            ColorSection(MinecraftColor.GOLD, 1),
            ColorSection(MinecraftColor.YELLOW, 1),
            ColorSection(MinecraftColor.GREEN, 1),
            ColorSection(MinecraftColor.AQUA, 1),
        )
    elif prestige == 11:
        color_sections = (ColorSection(MinecraftColor.WHITE, 4),)
    elif prestige == 12:
        color_sections = (ColorSection(MinecraftColor.YELLOW, 4),)
    elif prestige == 13:
        color_sections = (ColorSection(MinecraftColor.AQUA, 4),)
    elif prestige == 14:
        color_sections = (ColorSection(MinecraftColor.GREEN, 4),)
    elif prestige == 15:
        color_sections = (ColorSection(MinecraftColor.DARK_AQUA, 4),)
    elif prestige == 16:
        color_sections = (ColorSection(MinecraftColor.RED, 4),)
    elif prestige == 17:
        color_sections = (ColorSection(MinecraftColor.LIGHT_PURPLE, 4),)
    elif prestige == 18:
        color_sections = (ColorSection(MinecraftColor.BLUE, 4),)
    elif prestige == 19:
        color_sections = (ColorSection(MinecraftColor.DARK_PURPLE, 4),)
    elif prestige == 20:
        color_sections = (
            ColorSection(MinecraftColor.GRAY, 1),
            ColorSection(MinecraftColor.WHITE, 2),
            ColorSection(MinecraftColor.GRAY, 1),
        )
    elif prestige == 21:
        color_sections = (
            ColorSection(MinecraftColor.WHITE, 1),
            ColorSection(MinecraftColor.YELLOW, 2),
            ColorSection(MinecraftColor.GOLD, 1),
        )
    elif prestige == 22:
        color_sections = (
            ColorSection(MinecraftColor.GOLD, 1),
            ColorSection(MinecraftColor.WHITE, 2),
            ColorSection(MinecraftColor.AQUA, 1),
        )
    elif prestige == 23:
        color_sections = (
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
            ColorSection(MinecraftColor.LIGHT_PURPLE, 2),
            ColorSection(MinecraftColor.GOLD, 1),
        )
    elif prestige == 24:
        color_sections = (
            ColorSection(MinecraftColor.AQUA, 1),
            ColorSection(MinecraftColor.WHITE, 2),
            ColorSection(MinecraftColor.GRAY, 1),
        )
    elif prestige == 25:
        color_sections = (
            ColorSection(MinecraftColor.WHITE, 1),
            ColorSection(MinecraftColor.GREEN, 2),
            ColorSection(MinecraftColor.DARK_GREEN, 1),
        )
    elif prestige == 26:
        color_sections = (
            ColorSection(MinecraftColor.DARK_RED, 1),
            ColorSection(MinecraftColor.RED, 2),
            ColorSection(MinecraftColor.LIGHT_PURPLE, 1),
        )
    elif prestige == 27:
        color_sections = (
            ColorSection(MinecraftColor.YELLOW, 1),
            ColorSection(MinecraftColor.WHITE, 2),
            ColorSection(MinecraftColor.DARK_GRAY, 1),
        )
    elif prestige == 28:
        color_sections = (
            ColorSection(MinecraftColor.GREEN, 1),
            ColorSection(MinecraftColor.DARK_GREEN, 2),
            ColorSection(MinecraftColor.GOLD, 1),
        )
    elif prestige == 29:
        color_sections = (
            ColorSection(MinecraftColor.AQUA, 1),
            ColorSection(MinecraftColor.DARK_AQUA, 2),
            ColorSection(MinecraftColor.BLUE, 1),
        )
    else:  # >=3000 stars
        color_sections = (
            ColorSection(MinecraftColor.YELLOW, 1),
            ColorSection(MinecraftColor.GOLD, 2),
            ColorSection(MinecraftColor.RED, 1),
        )

    decimal_color_section = ColorSection(MinecraftColor.GRAY, -1)
    color_sections = color_sections + (decimal_color_section,)

    # Use regular level based rating for console, and actual star colors in the GUI
    return replace(
        render_based_on_level(text, stars, levels), color_sections=color_sections
    )


@lru_cache(maxsize=100)
def render_stats(
    player: "Player", rating_configs: RatingConfigCollection
) -> RenderedStats:
    username_str = player.username

    if isinstance(player, KnownPlayer):
        username_str = player.username + (
            f" ({player.nick})" if player.nick is not None else ""
        )

        stars_cell = render_stars(
            player.stars, rating_configs.stars.decimals, rating_configs.stars.levels
        )
        fkdr_cell = render_based_on_level(
            truncate_float_or_int(player.stats.fkdr, rating_configs.fkdr.decimals),
            player.stats.fkdr,
            rating_configs.fkdr.levels,
        )
        wlr_cell = render_based_on_level(
            truncate_float_or_int(player.stats.wlr, rating_configs.wlr.decimals),
            player.stats.wlr,
            rating_configs.wlr.levels,
        )
        if player.stats.winstreak is not None:
            winstreak_str = (
                "" if player.stats.winstreak_accurate else "~"
            ) + f"{player.stats.winstreak}"
        else:
            winstreak_str = "-"
        winstreak_cell = render_based_on_level(
            winstreak_str, player.stats.winstreak or 0, rating_configs.winstreak.levels
        )
    else:
        if isinstance(player, NickedPlayer):
            text = "unknown"
            terminal_formatting = TERMINAL_FORMATTINGS[-1]
            gui_color = GUI_COLORS[-1]
        elif isinstance(player, PendingPlayer):
            text = "-"
            terminal_formatting = TERMINAL_FORMATTINGS[0]
            gui_color = GUI_COLORS[0]
        else:  # pragma: no coverage
            assert_never(player)

        stars_cell = fkdr_cell = wlr_cell = winstreak_cell = CellValue.monochrome(
            text, terminal_formatting=terminal_formatting, gui_color=gui_color
        )

    username_cell = CellValue.monochrome(
        username_str,
        terminal_formatting=TerminalColor.LIGHT_WHITE,
        gui_color=GUIColor.WHITE,
    )

    return RenderedStats(
        username=username_cell,
        stars=stars_cell,
        fkdr=fkdr_cell,
        wlr=wlr_cell,
        winstreak=winstreak_cell,
    )


def pick_columns(
    rendered_stats: RenderedStats, column_names: tuple[ColumnName, ...]
) -> tuple[CellValue, ...]:
    """Pick the listed property names from the RenderedStats instance"""
    return tuple(getattr(rendered_stats, column_name) for column_name in column_names)
