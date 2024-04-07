from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import replace

import pytest

from prism.overlay.output.cell_renderer import (
    GUI_COLORS,
    TERMINAL_FORMATTINGS,
    RenderedStats,
    pick_columns,
    rate_value_ascending,
    rate_value_descending,
    render_based_on_level,
    render_stars,
)
from prism.overlay.output.cells import (
    ALL_COLUMN_NAMES_ORDERED,
    CellValue,
    ColorSection,
    ColumnName,
)
from prism.overlay.output.color import MinecraftColor, TerminalColor

LEVELS = (0.1, 0.5, 1, 10, 100)

# Tuples (value, rating) wrt LEVELS
RATE_VALUE_DESCENDING_CASES: tuple[tuple[float, int], ...] = (
    (0, 0),
    (0.0, 0),
    (0.05, 0),
    (0.1, 1),
    (0.2, 1),
    (0.49, 1),
    (0.50, 2),
    (0.70, 2),
    (1, 3),
    (1.0, 3),
    (1.5, 3),
    (5, 3),
    (10, 4),
    (50, 4),
    (50.1, 4),
    (100, 5),
    (1000, 5),
    (float("inf"), 5),
    (-1, 0),
    (-float("inf"), 0),
)

RATE_VALUE_ASCENDING_CASES: tuple[tuple[float, int], ...] = (
    (0, 5),
    (0.0, 5),
    (0.05, 5),
    (0.1, 5),
    (0.2, 4),
    (0.49, 4),
    (0.50, 4),
    (0.70, 3),
    (1, 3),
    (1.0, 3),
    (1.5, 2),
    (5, 2),
    (10, 2),
    (50, 1),
    (50.1, 1),
    (100, 1),
    (1000, 0),
    (float("inf"), 0),
    (-1, 5),
    (-float("inf"), 5),
)


@pytest.mark.parametrize("value, rating", RATE_VALUE_DESCENDING_CASES)
def test_rate_value_descending(
    value: float, rating: int, levels: Sequence[float] = LEVELS
) -> None:
    """Assert that rate_value_descending functions properly"""
    assert rate_value_descending(value, levels) == rating


@pytest.mark.parametrize("value, rating", RATE_VALUE_ASCENDING_CASES)
def test_rate_value_ascending(
    value: float, rating: int, levels: Sequence[float] = tuple(reversed(LEVELS))
) -> None:
    """Assert that rate_value_ascending functions properly"""
    assert rate_value_ascending(value, levels) == rating


STAR_LEVELS = (400.0, 800.0, 1600.0, 2900.0)
TF0, TF1, TF2, TF3, TF4 = TERMINAL_FORMATTINGS
PRESTIGE_COLORS = OrderedDict[str, tuple[str, tuple[ColorSection, ...]]](
    low_stone=(TF0, (ColorSection(MinecraftColor.GRAY, 1),)),
    stone=(TF0, (ColorSection(MinecraftColor.GRAY, 2),)),
    iron=(TF0, (ColorSection(MinecraftColor.WHITE, 3),)),
    gold=(TF0, (ColorSection(MinecraftColor.GOLD, 3),)),
    diamond=(TF0, (ColorSection(MinecraftColor.AQUA, 3),)),
    emerald=(TF1, (ColorSection(MinecraftColor.DARK_GREEN, 3),)),
    sapphire=(TF1, (ColorSection(MinecraftColor.DARK_AQUA, 3),)),
    ruby=(TF1, (ColorSection(MinecraftColor.DARK_RED, 3),)),
    crystal=(TF1, (ColorSection(MinecraftColor.LIGHT_PURPLE, 3),)),
    opal=(TF2, (ColorSection(MinecraftColor.BLUE, 3),)),
    amethyst=(TF2, (ColorSection(MinecraftColor.DARK_PURPLE, 3),)),
    rainbow=(
        TF2,
        (
            ColorSection(MinecraftColor.GOLD, 1),
            ColorSection(MinecraftColor.YELLOW, 1),
            ColorSection(MinecraftColor.GREEN, 1),
            ColorSection(MinecraftColor.AQUA, 1),
        ),
    ),
    iron_prime=(TF2, (ColorSection(MinecraftColor.WHITE, 4),)),
    gold_prime=(TF2, (ColorSection(MinecraftColor.YELLOW, 4),)),
    diamond_prime=(TF2, (ColorSection(MinecraftColor.AQUA, 4),)),
    emerald_prime=(TF2, (ColorSection(MinecraftColor.GREEN, 4),)),
    sapphire_prime=(TF2, (ColorSection(MinecraftColor.DARK_AQUA, 4),)),
    ruby_prime=(TF3, (ColorSection(MinecraftColor.RED, 4),)),
    crystal_prime=(TF3, (ColorSection(MinecraftColor.LIGHT_PURPLE, 4),)),
    opal_prime=(TF3, (ColorSection(MinecraftColor.BLUE, 4),)),
    amethyst_prime=(TF3, (ColorSection(MinecraftColor.DARK_PURPLE, 4),)),
    mirror=(
        TF3,
        (
            ColorSection(MinecraftColor.GRAY, 1),
            ColorSection(MinecraftColor.WHITE, 2),
            ColorSection(MinecraftColor.GRAY, 1),
        ),
    ),
    light=(
        TF3,
        (
            ColorSection(MinecraftColor.WHITE, 1),
            ColorSection(MinecraftColor.YELLOW, 2),
            ColorSection(MinecraftColor.GOLD, 1),
        ),
    ),
    dawn=(
        TF3,
        (
            ColorSection(MinecraftColor.GOLD, 1),
            ColorSection(MinecraftColor.WHITE, 2),
            ColorSection(MinecraftColor.AQUA, 1),
        ),
    ),
    dusk=(
        TF3,
        (
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
            ColorSection(MinecraftColor.LIGHT_PURPLE, 2),
            ColorSection(MinecraftColor.GOLD, 1),
        ),
    ),
    air=(
        TF3,
        (
            ColorSection(MinecraftColor.AQUA, 1),
            ColorSection(MinecraftColor.WHITE, 2),
            ColorSection(MinecraftColor.GRAY, 1),
        ),
    ),
    wind=(
        TF3,
        (
            ColorSection(MinecraftColor.WHITE, 1),
            ColorSection(MinecraftColor.GREEN, 2),
            ColorSection(MinecraftColor.DARK_GREEN, 1),
        ),
    ),
    nebula=(
        TF3,
        (
            ColorSection(MinecraftColor.DARK_RED, 1),
            ColorSection(MinecraftColor.RED, 2),
            ColorSection(MinecraftColor.LIGHT_PURPLE, 1),
        ),
    ),
    thunder=(
        TF3,
        (
            ColorSection(MinecraftColor.YELLOW, 1),
            ColorSection(MinecraftColor.WHITE, 2),
            ColorSection(MinecraftColor.DARK_GRAY, 1),
        ),
    ),
    earth=(
        TF3,
        (
            ColorSection(MinecraftColor.GREEN, 1),
            ColorSection(MinecraftColor.DARK_GREEN, 2),
            ColorSection(MinecraftColor.GOLD, 1),
        ),
    ),
    water=(
        TF4,
        (
            ColorSection(MinecraftColor.AQUA, 1),
            ColorSection(MinecraftColor.DARK_AQUA, 2),
            ColorSection(MinecraftColor.BLUE, 1),
        ),
    ),
    fire=(
        TF4,
        (
            ColorSection(MinecraftColor.YELLOW, 1),
            ColorSection(MinecraftColor.GOLD, 2),
            ColorSection(MinecraftColor.RED, 1),
        ),
    ),
    # Names for 3100-500 based on:
    # https://twitter.com/xopmine/status/1653790502024560641
    sunrise=(
        TF4,
        (
            ColorSection(MinecraftColor.BLUE, 1),
            ColorSection(MinecraftColor.DARK_AQUA, 2),
            ColorSection(MinecraftColor.GOLD, 1),
        ),
    ),
    eclipse=(
        TF4,
        (
            ColorSection(MinecraftColor.DARK_RED, 1),
            ColorSection(MinecraftColor.GRAY, 2),
            ColorSection(MinecraftColor.DARK_RED, 1),
        ),
    ),
    gamma=(
        TF4,
        (
            ColorSection(MinecraftColor.BLUE, 2),
            ColorSection(MinecraftColor.LIGHT_PURPLE, 1),
            ColorSection(MinecraftColor.RED, 1),
        ),
    ),
    majestic=(
        TF4,
        (
            ColorSection(MinecraftColor.GREEN, 1),
            ColorSection(MinecraftColor.LIGHT_PURPLE, 2),
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
        ),
    ),
    andesine=(
        TF4,
        (
            ColorSection(MinecraftColor.RED, 1),
            ColorSection(MinecraftColor.DARK_RED, 2),
            ColorSection(MinecraftColor.DARK_GREEN, 1),
        ),
    ),
    marine=(
        TF4,
        (
            ColorSection(MinecraftColor.GREEN, 2),
            ColorSection(MinecraftColor.AQUA, 1),
            ColorSection(MinecraftColor.BLUE, 1),
        ),
    ),
    element=(
        TF4,
        (
            ColorSection(MinecraftColor.DARK_RED, 1),
            ColorSection(MinecraftColor.RED, 2),
            ColorSection(MinecraftColor.AQUA, 1),
        ),
    ),
    galaxy=(
        TF4,
        (
            ColorSection(MinecraftColor.DARK_BLUE, 1),
            ColorSection(MinecraftColor.BLUE, 1),
            ColorSection(MinecraftColor.DARK_PURPLE, 2),
        ),
    ),
    atomic=(
        TF4,
        (
            ColorSection(MinecraftColor.RED, 1),
            ColorSection(MinecraftColor.GREEN, 2),
            ColorSection(MinecraftColor.DARK_AQUA, 1),
        ),
    ),
    sunset=(
        TF4,
        (
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
            ColorSection(MinecraftColor.RED, 2),
            ColorSection(MinecraftColor.GOLD, 1),
        ),
    ),
    time=(
        TF4,
        (
            ColorSection(MinecraftColor.YELLOW, 1),
            ColorSection(MinecraftColor.GOLD, 1),
            ColorSection(MinecraftColor.RED, 1),
            ColorSection(MinecraftColor.LIGHT_PURPLE, 1),
        ),
    ),
    winter=(
        TF4,
        (
            ColorSection(MinecraftColor.BLUE, 1),
            ColorSection(MinecraftColor.DARK_AQUA, 1),
            ColorSection(MinecraftColor.AQUA, 1),
            ColorSection(MinecraftColor.WHITE, 1),
        ),
    ),
    obsidian=(
        TF4,
        (
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
            ColorSection(MinecraftColor.DARK_GRAY, 2),
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
        ),
    ),
    spring=(
        TF4,
        (
            ColorSection(MinecraftColor.DARK_GREEN, 1),
            ColorSection(MinecraftColor.GREEN, 1),
            ColorSection(MinecraftColor.YELLOW, 1),
            ColorSection(MinecraftColor.GOLD, 1),
        ),
    ),
    ice=(
        TF4,
        (
            ColorSection(MinecraftColor.WHITE, 1),
            ColorSection(MinecraftColor.AQUA, 2),
            ColorSection(MinecraftColor.DARK_AQUA, 1),
        ),
    ),
    summer=(
        TF4,
        (
            ColorSection(MinecraftColor.AQUA, 1),
            ColorSection(MinecraftColor.YELLOW, 2),
            ColorSection(MinecraftColor.GOLD, 1),
        ),
    ),
    spinel=(
        TF4,
        (
            ColorSection(MinecraftColor.DARK_RED, 1),
            ColorSection(MinecraftColor.RED, 2),
            ColorSection(MinecraftColor.BLUE, 1),
        ),
    ),
    autumn=(
        TF4,
        (
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
            ColorSection(MinecraftColor.RED, 1),
            ColorSection(MinecraftColor.GOLD, 1),
            ColorSection(MinecraftColor.YELLOW, 1),
        ),
    ),
    mystic=(
        TF4,
        (
            ColorSection(MinecraftColor.GREEN, 1),
            ColorSection(MinecraftColor.WHITE, 2),
            ColorSection(MinecraftColor.GREEN, 1),
        ),
    ),
    eternal=(
        TF4,
        (
            ColorSection(MinecraftColor.DARK_RED, 1),
            ColorSection(MinecraftColor.DARK_PURPLE, 1),
            ColorSection(MinecraftColor.BLUE, 2),
        ),
    ),
)


def make_star_cell_value(text: str, prestige: str) -> CellValue:
    terminal_formatting, color_sections = PRESTIGE_COLORS[prestige]
    return CellValue(
        text,
        terminal_formatting,
        color_sections + (ColorSection(MinecraftColor.GRAY, -1),),
    )


RENDER_STARS_CASES: tuple[tuple[float, int, CellValue], ...] = (
    (0, 0, make_star_cell_value("0", "low_stone")),
    (0, 1, make_star_cell_value("0.0", "low_stone")),
    (0, 2, make_star_cell_value("0.00", "low_stone")),
    (9.199, 2, make_star_cell_value("9.19", "low_stone")),
    (10.5, 2, make_star_cell_value("10.50", "stone")),
    *(
        (
            prestige * 100 + 50.99,
            2,
            make_star_cell_value(
                f"{prestige if prestige > 0 else ''}50.99", prestige_name
            ),
        )
        # Iterate over all prestiges in order (skip low_stone)
        for prestige, prestige_name in zip(
            range(51), tuple(PRESTIGE_COLORS)[1:], strict=True
        )
    ),
    (
        5500.18324,
        2,
        CellValue(
            "5500.18",
            TF4,
            (
                ColorSection(MinecraftColor.DARK_RED, 1),
                ColorSection(MinecraftColor.DARK_PURPLE, 1),
                ColorSection(MinecraftColor.BLUE, 2),
                ColorSection(MinecraftColor.GRAY, -1),
            ),
        ),
    ),
    (
        10_000.18324,
        2,
        CellValue(
            "10000.18",
            TF4,
            (
                ColorSection(MinecraftColor.DARK_RED, 1),
                ColorSection(MinecraftColor.DARK_PURPLE, 1),
                ColorSection(MinecraftColor.BLUE, 3),
                ColorSection(MinecraftColor.GRAY, -1),
            ),
        ),
    ),
    (
        100_000.18324,
        2,
        CellValue(
            "100000.18",
            TF4,
            (
                ColorSection(MinecraftColor.DARK_RED, 1),
                ColorSection(MinecraftColor.DARK_PURPLE, 1),
                ColorSection(MinecraftColor.BLUE, 4),
                ColorSection(MinecraftColor.GRAY, -1),
            ),
        ),
    ),
)


@pytest.mark.parametrize("stars, decimals, cell_value", RENDER_STARS_CASES)
def test_render_stars(
    stars: float,
    decimals: int,
    cell_value: CellValue,
    levels: tuple[float, ...] = STAR_LEVELS,
) -> None:
    assert (
        render_stars(
            stars, decimals, levels, use_star_colors=True, sort_ascending=False
        )
        == cell_value
    )

    cell_value_no_star_color = replace(
        cell_value,
        color_sections=(
            ColorSection(
                GUI_COLORS[TERMINAL_FORMATTINGS.index(cell_value.terminal_formatting)],
                -1,
            ),
        ),
    )
    assert (
        render_stars(
            stars, decimals, levels, use_star_colors=False, sort_ascending=False
        )
        == cell_value_no_star_color
    )


USERNAME_VALUE = CellValue.monochrome(
    "username",
    terminal_formatting=TerminalColor.RED,
    gui_color=MinecraftColor.LIGHT_PURPLE,
)
STARS_VALUE = CellValue.monochrome(
    "stars",
    terminal_formatting=TerminalColor.BLUE,
    gui_color=MinecraftColor.DARK_PURPLE,
)
INDEX_VALUE = CellValue.monochrome(
    "index",
    terminal_formatting=TerminalColor.BLACK,
    gui_color=MinecraftColor.LIGHT_PURPLE,
)
FKDR_VALUE = CellValue.monochrome(
    "fkdr", terminal_formatting=TerminalColor.LIGHT_WHITE, gui_color=MinecraftColor.GRAY
)
KDR_VALUE = CellValue.monochrome(
    "kdr", terminal_formatting=TerminalColor.YELLOW, gui_color=MinecraftColor.GREEN
)
BBLR_VALUE = CellValue.monochrome(
    "bblr", terminal_formatting=TerminalColor.BROWN, gui_color=MinecraftColor.DARK_GREEN
)
WLR_VALUE = CellValue.monochrome(
    "wlr", terminal_formatting=TerminalColor.GREEN, gui_color=MinecraftColor.AQUA
)
WINSTREAK_VALUE = CellValue.monochrome(
    "winstreak",
    terminal_formatting=TerminalColor.YELLOW,
    gui_color=MinecraftColor.GREEN,
)
KILLS_VALUE = CellValue.monochrome(
    "kills", terminal_formatting=TerminalColor.CYAN, gui_color=MinecraftColor.GOLD
)
FINALS_VALUE = CellValue.monochrome(
    "finals",
    terminal_formatting=TerminalColor.RED,
    gui_color=MinecraftColor.LIGHT_PURPLE,
)
BEDS_VALUE = CellValue.monochrome(
    "beds", terminal_formatting=TerminalColor.PURPLE, gui_color=MinecraftColor.RED
)
WINS_VALUE = CellValue.monochrome(
    "wins", terminal_formatting=TerminalColor.DARK_GRAY, gui_color=MinecraftColor.AQUA
)
RENDERED_STATS = RenderedStats(
    username=USERNAME_VALUE,
    stars=STARS_VALUE,
    index=INDEX_VALUE,
    fkdr=FKDR_VALUE,
    kdr=KDR_VALUE,
    bblr=BBLR_VALUE,
    wlr=WLR_VALUE,
    winstreak=WINSTREAK_VALUE,
    kills=KILLS_VALUE,
    finals=FINALS_VALUE,
    beds=BEDS_VALUE,
    wins=WINS_VALUE,
)


PICK_COLUMNS_CASES: tuple[tuple[tuple[ColumnName, ...], tuple[CellValue, ...]], ...] = (
    (("username", "stars"), (USERNAME_VALUE, STARS_VALUE)),
    (
        ("username", "stars", "fkdr", "wlr", "winstreak"),
        (USERNAME_VALUE, STARS_VALUE, FKDR_VALUE, WLR_VALUE, WINSTREAK_VALUE),
    ),
    (("username", "stars", "stars"), (USERNAME_VALUE, STARS_VALUE, STARS_VALUE)),
    (
        ("username", "index", "kdr", "finals"),
        (USERNAME_VALUE, INDEX_VALUE, KDR_VALUE, FINALS_VALUE),
    ),
    (
        ALL_COLUMN_NAMES_ORDERED,
        (
            USERNAME_VALUE,
            STARS_VALUE,
            INDEX_VALUE,
            FKDR_VALUE,
            KDR_VALUE,
            BBLR_VALUE,
            WLR_VALUE,
            WINSTREAK_VALUE,
            KILLS_VALUE,
            FINALS_VALUE,
            BEDS_VALUE,
            WINS_VALUE,
        ),
    ),
)


@pytest.mark.parametrize("column_names, result", PICK_COLUMNS_CASES)
def test_pick_columns(
    column_names: tuple[ColumnName, ...], result: tuple[CellValue, ...]
) -> None:
    assert pick_columns(RENDERED_STATS, column_names) == result


@pytest.mark.parametrize(
    "text, value, rate_by_level, sort_ascending, target",
    (
        (
            "a",
            0,
            True,
            False,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[0], GUI_COLORS[0]),
        ),
        (
            "a",
            0,
            False,
            False,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[1], GUI_COLORS[1]),
        ),
        (
            "a",
            0.1,
            True,
            False,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[1], GUI_COLORS[1]),
        ),
        (
            "a",
            0.1,
            False,
            False,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[1], GUI_COLORS[1]),
        ),
        (
            "a",
            0.5,
            True,
            False,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[2], GUI_COLORS[2]),
        ),
        (
            "a",
            0.5,
            False,
            False,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[1], GUI_COLORS[1]),
        ),
        (
            "a",
            1,
            True,
            False,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[3], GUI_COLORS[3]),
        ),
        (
            "a",
            1,
            False,
            False,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[1], GUI_COLORS[1]),
        ),
        # Ascending
        (
            "a",
            0,
            True,
            True,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[4], GUI_COLORS[4]),
        ),
        (
            "a",
            0.01,
            True,
            True,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[4], GUI_COLORS[4]),
        ),
        (
            "a",
            0.1,
            True,
            True,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[4], GUI_COLORS[4]),
        ),
        (
            "a",
            0.5,
            True,
            True,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[3], GUI_COLORS[3]),
        ),
        (
            "a",
            0.8,
            True,
            True,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[2], GUI_COLORS[2]),
        ),
        (
            "a",
            1.0,
            True,
            True,
            CellValue.monochrome("a", TERMINAL_FORMATTINGS[2], GUI_COLORS[2]),
        ),
    ),
)
def test_render_based_on_level(
    text: str,
    value: float,
    rate_by_level: bool,
    sort_ascending: bool,
    target: CellValue,
) -> None:
    levels: tuple[float, ...] = (0.1, 0.5, 1, 10)
    levels = tuple(reversed(levels)) if sort_ascending else levels
    assert (
        render_based_on_level(text, value, levels, rate_by_level, sort_ascending)
        == target
    )


def test_render_based_on_level_too_many_levels() -> None:
    assert render_based_on_level(
        "a", 100, (1, 2, 3, 4, 5, 6, 7, 8), True, sort_ascending=False
    ) == CellValue.monochrome("a", TERMINAL_FORMATTINGS[4], GUI_COLORS[4])
