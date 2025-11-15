from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Literal, assert_never

from prism.overlay.output.cells import (
    AMT_COLORS,
    GUI_COLORS,
    CellValue,
    ColorSection,
    ColumnName,
)
from prism.overlay.output.color import GUIColor, MinecraftColor
from prism.overlay.output.config import RatingConfig, RatingConfigCollection
from prism.player import (
    KnownPlayer,
    NickedPlayer,
    PendingPlayer,
    Player,
    Tags,
    TagSeverity,
    UnknownPlayer,
)
from prism.utils import format_seconds_short, truncate_float


@dataclass(frozen=True, slots=True)
class RenderedStats:
    """Colored CellValues based on the rating for each stat"""

    username: CellValue
    stars: CellValue
    index: CellValue
    fkdr: CellValue
    kdr: CellValue
    bblr: CellValue
    wlr: CellValue
    winstreak: CellValue
    kills: CellValue
    finals: CellValue
    beds: CellValue
    wins: CellValue
    sessiontime: CellValue

    tags: CellValue


def truncate_float_or_int(value: float | int, decimals: int) -> str:
    """Truncate the decimals of the float, or keep the int"""
    if isinstance(value, int):
        return str(value)
    return truncate_float(value, decimals)


def rate_value_descending(value: float, levels: Sequence[float]) -> int:
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


def rate_value_ascending(value: float, levels: Sequence[float]) -> int:
    """Like rate_value_descending but with low values rated highly"""
    for rating, level in enumerate(levels):
        if value > level:
            return rating

    # Passed all levels
    return rating + 1


def missing_stat_value(rating_config: RatingConfig) -> float:
    """
    Return the value that should be used for a missing stat

    Ensures that missing stats are sorted to the top
    """
    return float("-inf") if rating_config.sort_ascending else float("inf")


def render_based_on_level(
    text: str,
    value: int | float,
    levels: tuple[float, ...],
    rate_by_level: bool,
    sort_ascending: bool,
) -> CellValue:
    rate_value = rate_value_ascending if sort_ascending else rate_value_descending
    if rate_by_level:
        rating = min(rate_value(value, levels), AMT_COLORS - 1)
        gui_color = GUI_COLORS[rating]
    else:
        gui_color = GUI_COLORS[1]

    return CellValue.monochrome(text=text, gui_color=gui_color)


def render_stars(
    stars: float,
    decimals: int,
    levels: tuple[float, ...],
    use_star_colors: bool,
    sort_ascending: bool,
) -> CellValue:
    """
    Render the user's star using the Hypixel BedWars star colors

    Source (0-3000): https://hypixel.net/threads/tool-bedwars-prestige-colors-in-minecraft-color-code-and-hex-code-high-effort-post.3841719/
    Source (3100-5000): https://hypixel.net/threads/bed-wars-update-new-practice-modes-qol-changes-more.5339873/
    """  # noqa: E501
    text = truncate_float(stars, decimals)

    levels_rating = render_based_on_level(text, stars, levels, True, sort_ascending)
    if not use_star_colors:
        return levels_rating

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
    elif prestige == 30:
        color_sections = (
            ColorSection(MinecraftColor.YELLOW, 1),
            ColorSection(MinecraftColor.GOLD, 2),
            ColorSection(MinecraftColor.RED, 1),
        )
    elif prestige == 31:
        color_sections = (
            ColorSection(MinecraftColor.BLUE, 1),
            ColorSection(MinecraftColor.DARK_AQUA, 2),
            ColorSection(MinecraftColor.GOLD, 1),
        )
    elif prestige == 32:
        color_sections = (
            ColorSection(MinecraftColor.DARK_RED, 1),
            ColorSection(MinecraftColor.GRAY, 2),
            ColorSection(MinecraftColor.DARK_RED, 1),
        )
    elif prestige == 33:
        color_sections = (
            ColorSection(MinecraftColor.BLUE, 2),
            ColorSection(MinecraftColor.LIGHT_PURPLE, 1),
            ColorSection(MinecraftColor.RED, 1),
        )
    elif prestige == 34:
        color_sections = (
            ColorSection(MinecraftColor.GREEN, 1),
            ColorSection(MinecraftColor.LIGHT_PURPLE, 2),
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
        )
    elif prestige == 35:
        color_sections = (
            ColorSection(MinecraftColor.RED, 1),
            ColorSection(MinecraftColor.DARK_RED, 2),
            ColorSection(MinecraftColor.DARK_GREEN, 1),
        )
    elif prestige == 36:
        color_sections = (
            ColorSection(MinecraftColor.GREEN, 2),
            ColorSection(MinecraftColor.AQUA, 1),
            ColorSection(MinecraftColor.BLUE, 1),
        )
    elif prestige == 37:
        color_sections = (
            ColorSection(MinecraftColor.DARK_RED, 1),
            ColorSection(MinecraftColor.RED, 2),
            ColorSection(MinecraftColor.AQUA, 1),
        )
    elif prestige == 38:
        color_sections = (
            ColorSection(MinecraftColor.DARK_BLUE, 1),
            ColorSection(MinecraftColor.BLUE, 1),
            ColorSection(MinecraftColor.DARK_PURPLE, 2),
        )
    elif prestige == 39:
        color_sections = (
            ColorSection(MinecraftColor.RED, 1),
            ColorSection(MinecraftColor.GREEN, 2),
            ColorSection(MinecraftColor.DARK_AQUA, 1),
        )
    elif prestige == 40:
        color_sections = (
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
            ColorSection(MinecraftColor.RED, 2),
            ColorSection(MinecraftColor.GOLD, 1),
        )
    elif prestige == 41:
        color_sections = (
            ColorSection(MinecraftColor.YELLOW, 1),
            ColorSection(MinecraftColor.GOLD, 1),
            ColorSection(MinecraftColor.RED, 1),
            ColorSection(MinecraftColor.LIGHT_PURPLE, 1),
        )
    elif prestige == 42:
        color_sections = (
            ColorSection(MinecraftColor.BLUE, 1),
            ColorSection(MinecraftColor.DARK_AQUA, 1),
            ColorSection(MinecraftColor.AQUA, 1),
            ColorSection(MinecraftColor.WHITE, 1),
        )
    elif prestige == 43:
        color_sections = (
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
            ColorSection(MinecraftColor.DARK_GRAY, 2),
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
        )
    elif prestige == 44:
        color_sections = (
            ColorSection(MinecraftColor.DARK_GREEN, 1),
            ColorSection(MinecraftColor.GREEN, 1),
            ColorSection(MinecraftColor.YELLOW, 1),
            ColorSection(MinecraftColor.GOLD, 1),
        )
    elif prestige == 45:
        color_sections = (
            ColorSection(MinecraftColor.WHITE, 1),
            ColorSection(MinecraftColor.AQUA, 2),
            ColorSection(MinecraftColor.DARK_AQUA, 1),
        )
    elif prestige == 46:
        color_sections = (
            ColorSection(MinecraftColor.AQUA, 1),
            ColorSection(MinecraftColor.YELLOW, 2),
            ColorSection(MinecraftColor.GOLD, 1),
        )
    elif prestige == 47:
        color_sections = (
            ColorSection(MinecraftColor.DARK_RED, 1),
            ColorSection(MinecraftColor.RED, 2),
            ColorSection(MinecraftColor.BLUE, 1),
        )
    elif prestige == 48:
        color_sections = (
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
            ColorSection(MinecraftColor.RED, 1),
            ColorSection(MinecraftColor.GOLD, 1),
            ColorSection(MinecraftColor.YELLOW, 1),
        )
    elif prestige == 49:
        color_sections = (
            ColorSection(MinecraftColor.GREEN, 1),
            ColorSection(MinecraftColor.WHITE, 2),
            ColorSection(MinecraftColor.GREEN, 1),
        )
    else:  # >=5000 stars
        star_digit_count = len(str(prestige)) + 2
        color_sections = (
            ColorSection(MinecraftColor.DARK_RED, 1),
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
            # For prestige == 50, star_digit_count - 2 == 2
            # For stars >=10_000 we just make the rest of the numbers blue
            ColorSection(MinecraftColor.BLUE, star_digit_count - 2),
        )

    decimal_color_section = ColorSection(MinecraftColor.GRAY, -1)
    color_sections = color_sections + (decimal_color_section,)

    # Use regular level based rating for console, and actual star colors in the GUI
    return replace(levels_rating, color_sections=color_sections)


def tag_severity_to_color(severity: Literal["medium", "high"]) -> str:
    if severity == "medium":
        return GUI_COLORS[3]
    elif severity == "high":
        return GUI_COLORS[4]


def render_tags(tags: Tags | None) -> CellValue:
    if tags is None:
        return CellValue.pending()

    def add_tag(
        text: str,
        color_sections: tuple[ColorSection, ...],
        tag_char: str,
        severity: TagSeverity,
    ) -> tuple[str, tuple[ColorSection, ...]]:
        if severity == "none":
            return text, color_sections

        if text != "":
            # There is already a tag, add space separator
            text += " "
            color_sections += (ColorSection(GUI_COLORS[0], 1),)

        return (
            text + tag_char,
            color_sections + (ColorSection(tag_severity_to_color(severity), 1),),
        )

    color_sections: tuple[ColorSection, ...] = ()
    text = ""

    text, color_sections = add_tag(text, color_sections, "C", tags.cheating)
    text, color_sections = add_tag(text, color_sections, "S", tags.sniping)

    if len(color_sections) == 0:
        return CellValue.empty()

    return CellValue(text=text, color_sections=color_sections)


@lru_cache(maxsize=100)
def render_stats(
    player: Player,
    rating_configs: RatingConfigCollection,
) -> RenderedStats:
    username_str = player.username

    if isinstance(player, KnownPlayer):
        username_str = player.username + (
            f" ({player.nick})" if player.nick is not None else ""
        )

        stars_cell = render_stars(
            player.stars,
            rating_configs.stars.decimals,
            rating_configs.stars.levels,
            use_star_colors=not rating_configs.stars.rate_by_level,
            sort_ascending=rating_configs.index.sort_ascending,
        )
        index_cell = render_based_on_level(
            truncate_float_or_int(player.stats.index, rating_configs.index.decimals),
            player.stats.index,
            rating_configs.index.levels,
            rating_configs.index.rate_by_level,
            rating_configs.index.sort_ascending,
        )
        fkdr_cell = render_based_on_level(
            truncate_float_or_int(player.stats.fkdr, rating_configs.fkdr.decimals),
            player.stats.fkdr,
            rating_configs.fkdr.levels,
            rating_configs.fkdr.rate_by_level,
            rating_configs.fkdr.sort_ascending,
        )
        kdr_cell = render_based_on_level(
            truncate_float_or_int(player.stats.kdr, rating_configs.kdr.decimals),
            player.stats.kdr,
            rating_configs.kdr.levels,
            rating_configs.kdr.rate_by_level,
            rating_configs.kdr.sort_ascending,
        )
        bblr_cell = render_based_on_level(
            truncate_float_or_int(player.stats.bblr, rating_configs.bblr.decimals),
            player.stats.bblr,
            rating_configs.bblr.levels,
            rating_configs.bblr.rate_by_level,
            rating_configs.bblr.sort_ascending,
        )
        wlr_cell = render_based_on_level(
            truncate_float_or_int(player.stats.wlr, rating_configs.wlr.decimals),
            player.stats.wlr,
            rating_configs.wlr.levels,
            rating_configs.wlr.rate_by_level,
            rating_configs.wlr.sort_ascending,
        )
        if player.stats.winstreak is not None:
            winstreak_str = (
                "" if player.stats.winstreak_accurate else "~"
            ) + f"{player.stats.winstreak}"
            winstreak_value: float = player.stats.winstreak
        else:
            winstreak_str = "-"
            winstreak_value = missing_stat_value(rating_configs.winstreak)
        winstreak_cell = render_based_on_level(
            winstreak_str,
            winstreak_value,
            rating_configs.winstreak.levels,
            rating_configs.winstreak.rate_by_level,
            rating_configs.winstreak.sort_ascending,
        )
        kills_cell = render_based_on_level(
            truncate_float_or_int(player.stats.kills, rating_configs.kills.decimals),
            player.stats.kills,
            rating_configs.kills.levels,
            rating_configs.kills.rate_by_level,
            rating_configs.kills.sort_ascending,
        )
        finals_cell = render_based_on_level(
            truncate_float_or_int(player.stats.finals, rating_configs.finals.decimals),
            player.stats.finals,
            rating_configs.finals.levels,
            rating_configs.finals.rate_by_level,
            rating_configs.finals.sort_ascending,
        )
        beds_cell = render_based_on_level(
            truncate_float_or_int(player.stats.beds, rating_configs.beds.decimals),
            player.stats.beds,
            rating_configs.beds.levels,
            rating_configs.beds.rate_by_level,
            rating_configs.beds.sort_ascending,
        )
        wins_cell = render_based_on_level(
            truncate_float_or_int(player.stats.wins, rating_configs.wins.decimals),
            player.stats.wins,
            rating_configs.wins.levels,
            rating_configs.wins.rate_by_level,
            rating_configs.wins.sort_ascending,
        )
        if player.sessiontime_seconds is None:
            sessiontime_str = "-"
            sessiontime_value = missing_stat_value(rating_configs.sessiontime)
        else:
            sessiontime_str = format_seconds_short(
                player.sessiontime_seconds, rating_configs.sessiontime.decimals
            )
            # Convert to minutes, as that is the unit used in the rating config
            sessiontime_value = player.sessiontime_seconds / 60
        sessiontime_cell = render_based_on_level(
            sessiontime_str,
            sessiontime_value,
            rating_configs.sessiontime.levels,
            rating_configs.sessiontime.rate_by_level,
            rating_configs.sessiontime.sort_ascending,
        )
        tags_cell = render_tags(player.tags)
    else:
        if isinstance(player, NickedPlayer):
            cell = CellValue.nicked()
        elif isinstance(player, PendingPlayer):
            cell = CellValue.pending()
        elif isinstance(player, UnknownPlayer):
            cell = CellValue.error()
        else:  # pragma: no coverage
            assert_never(player)

        stars_cell = index_cell = fkdr_cell = kdr_cell = bblr_cell = wlr_cell = cell
        winstreak_cell = kills_cell = finals_cell = beds_cell = wins_cell = cell
        sessiontime_cell = tags_cell = cell

    username_cell = CellValue.monochrome(username_str, gui_color=GUIColor.WHITE)

    return RenderedStats(
        username=username_cell,
        stars=stars_cell,
        fkdr=fkdr_cell,
        index=index_cell,
        kdr=kdr_cell,
        bblr=bblr_cell,
        wlr=wlr_cell,
        winstreak=winstreak_cell,
        kills=kills_cell,
        finals=finals_cell,
        beds=beds_cell,
        wins=wins_cell,
        sessiontime=sessiontime_cell,
        tags=tags_cell,
    )


def pick_columns(
    rendered_stats: RenderedStats, column_names: tuple[ColumnName, ...]
) -> tuple[CellValue, ...]:
    """Pick the listed property names from the RenderedStats instance"""
    return tuple(getattr(rendered_stats, column_name) for column_name in column_names)
