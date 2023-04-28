from collections import OrderedDict
from collections.abc import Sequence

import pytest

from prism.overlay.output.cell_renderer import (
    TERMINAL_FORMATTINGS,
    RenderedStats,
    pick_columns,
    rate_value,
    render_stars,
)
from prism.overlay.output.cells import (
    ALL_COLUMN_NAMES,
    CellValue,
    ColorSection,
    ColumnName,
)
from prism.overlay.output.color import MinecraftColor, TerminalColor

LEVELS = (0.1, 0.5, 1, 10, 100)

# Tuples (value, rating) wrt LEVELS
RATE_VALUE_CASES: tuple[tuple[float, int], ...] = (
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


@pytest.mark.parametrize("value, rating", RATE_VALUE_CASES)
def test_rate_value(
    value: float, rating: int, levels: Sequence[float] = LEVELS
) -> None:
    """Assert that rate_value functions properly"""
    assert rate_value(value, levels) == rating


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
        for prestige, prestige_name in enumerate(tuple(PRESTIGE_COLORS)[1:])
    ),
)


@pytest.mark.parametrize("stars, decimals, cell_value", RENDER_STARS_CASES)
def test_render_stars(
    stars: float,
    decimals: int,
    cell_value: CellValue,
    levels: tuple[float, ...] = STAR_LEVELS,
) -> None:
    assert render_stars(stars, decimals, levels) == cell_value


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
FKDR_VALUE = CellValue.monochrome(
    "fkdr", terminal_formatting=TerminalColor.LIGHT_WHITE, gui_color=MinecraftColor.GRAY
)
WLR_VALUE = CellValue.monochrome(
    "wlr", terminal_formatting=TerminalColor.GREEN, gui_color=MinecraftColor.AQUA
)
WINSTREAK_VALUE = CellValue.monochrome(
    "winstreak",
    terminal_formatting=TerminalColor.YELLOW,
    gui_color=MinecraftColor.GREEN,
)
RENDERED_STATS = RenderedStats(
    username=USERNAME_VALUE,
    stars=STARS_VALUE,
    fkdr=FKDR_VALUE,
    wlr=WLR_VALUE,
    winstreak=WINSTREAK_VALUE,
)


PICK_COLUMNS_CASES: tuple[tuple[tuple[ColumnName, ...], tuple[CellValue, ...]], ...] = (
    (("username", "stars"), (USERNAME_VALUE, STARS_VALUE)),
    (
        ("username", "stars", "fkdr", "wlr", "winstreak"),
        (USERNAME_VALUE, STARS_VALUE, FKDR_VALUE, WLR_VALUE, WINSTREAK_VALUE),
    ),
    (("username", "stars", "stars"), (USERNAME_VALUE, STARS_VALUE, STARS_VALUE)),
    (
        tuple(sorted(ALL_COLUMN_NAMES)),
        (FKDR_VALUE, STARS_VALUE, USERNAME_VALUE, WINSTREAK_VALUE, WLR_VALUE),
    ),
)


@pytest.mark.parametrize("column_names, result", PICK_COLUMNS_CASES)
def test_pick_columns(
    column_names: tuple[ColumnName, ...], result: tuple[CellValue, ...]
) -> None:
    assert pick_columns(RENDERED_STATS, column_names) == result
