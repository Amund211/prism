from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import fields, replace

import pytest

from prism.overlay.output.cell_renderer import (
    RenderedStats,
    pick_columns,
    rate_value_ascending,
    rate_value_descending,
    render_based_on_level,
    render_stars,
    render_stats,
)
from prism.overlay.output.cells import (
    ALL_COLUMN_NAMES_ORDERED,
    GUI_COLORS,
    CellValue,
    ColorSection,
    ColumnName,
)
from prism.overlay.output.color import MinecraftColor
from prism.overlay.output.config import (
    DEFAULT_BBLR_CONFIG,
    DEFAULT_BEDS_CONFIG,
    DEFAULT_FINALS_CONFIG,
    DEFAULT_FKDR_CONFIG,
    DEFAULT_INDEX_CONFIG,
    DEFAULT_KDR_CONFIG,
    DEFAULT_KILLS_CONFIG,
    DEFAULT_SESSIONTIME_CONFIG,
    DEFAULT_STARS_CONFIG,
    DEFAULT_WINS_CONFIG,
    DEFAULT_WINSTREAK_CONFIG,
    DEFAULT_WLR_CONFIG,
    RatingConfig,
    RatingConfigCollection,
)
from prism.utils import truncate_float
from tests.prism.overlay.utils import make_player

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
PRESTIGE_COLORS = OrderedDict[str, tuple[ColorSection, ...]](
    low_stone=(ColorSection(MinecraftColor.GRAY, 1),),
    stone=(ColorSection(MinecraftColor.GRAY, 2),),
    iron=(ColorSection(MinecraftColor.WHITE, 3),),
    gold=(ColorSection(MinecraftColor.GOLD, 3),),
    diamond=(ColorSection(MinecraftColor.AQUA, 3),),
    emerald=(ColorSection(MinecraftColor.DARK_GREEN, 3),),
    sapphire=(ColorSection(MinecraftColor.DARK_AQUA, 3),),
    ruby=(ColorSection(MinecraftColor.DARK_RED, 3),),
    crystal=(ColorSection(MinecraftColor.LIGHT_PURPLE, 3),),
    opal=(ColorSection(MinecraftColor.BLUE, 3),),
    amethyst=(ColorSection(MinecraftColor.DARK_PURPLE, 3),),
    rainbow=(
        ColorSection(MinecraftColor.GOLD, 1),
        ColorSection(MinecraftColor.YELLOW, 1),
        ColorSection(MinecraftColor.GREEN, 1),
        ColorSection(MinecraftColor.AQUA, 1),
    ),
    iron_prime=(ColorSection(MinecraftColor.WHITE, 4),),
    gold_prime=(ColorSection(MinecraftColor.YELLOW, 4),),
    diamond_prime=(ColorSection(MinecraftColor.AQUA, 4),),
    emerald_prime=(ColorSection(MinecraftColor.GREEN, 4),),
    sapphire_prime=(ColorSection(MinecraftColor.DARK_AQUA, 4),),
    ruby_prime=(ColorSection(MinecraftColor.RED, 4),),
    crystal_prime=(ColorSection(MinecraftColor.LIGHT_PURPLE, 4),),
    opal_prime=(ColorSection(MinecraftColor.BLUE, 4),),
    amethyst_prime=(ColorSection(MinecraftColor.DARK_PURPLE, 4),),
    mirror=(
        ColorSection(MinecraftColor.GRAY, 1),
        ColorSection(MinecraftColor.WHITE, 2),
        ColorSection(MinecraftColor.GRAY, 1),
    ),
    light=(
        ColorSection(MinecraftColor.WHITE, 1),
        ColorSection(MinecraftColor.YELLOW, 2),
        ColorSection(MinecraftColor.GOLD, 1),
    ),
    dawn=(
        ColorSection(MinecraftColor.GOLD, 1),
        ColorSection(MinecraftColor.WHITE, 2),
        ColorSection(MinecraftColor.AQUA, 1),
    ),
    dusk=(
        ColorSection(MinecraftColor.DARK_PURPLE, 1),
        ColorSection(MinecraftColor.LIGHT_PURPLE, 2),
        ColorSection(MinecraftColor.GOLD, 1),
    ),
    air=(
        ColorSection(MinecraftColor.AQUA, 1),
        ColorSection(MinecraftColor.WHITE, 2),
        ColorSection(MinecraftColor.GRAY, 1),
    ),
    wind=(
        ColorSection(MinecraftColor.WHITE, 1),
        ColorSection(MinecraftColor.GREEN, 2),
        ColorSection(MinecraftColor.DARK_GREEN, 1),
    ),
    nebula=(
        ColorSection(MinecraftColor.DARK_RED, 1),
        ColorSection(MinecraftColor.RED, 2),
        ColorSection(MinecraftColor.LIGHT_PURPLE, 1),
    ),
    thunder=(
        ColorSection(MinecraftColor.YELLOW, 1),
        ColorSection(MinecraftColor.WHITE, 2),
        ColorSection(MinecraftColor.DARK_GRAY, 1),
    ),
    earth=(
        ColorSection(MinecraftColor.GREEN, 1),
        ColorSection(MinecraftColor.DARK_GREEN, 2),
        ColorSection(MinecraftColor.GOLD, 1),
    ),
    water=(
        ColorSection(MinecraftColor.AQUA, 1),
        ColorSection(MinecraftColor.DARK_AQUA, 2),
        ColorSection(MinecraftColor.BLUE, 1),
    ),
    fire=(
        ColorSection(MinecraftColor.YELLOW, 1),
        ColorSection(MinecraftColor.GOLD, 2),
        ColorSection(MinecraftColor.RED, 1),
    ),
    # Names for 3100-500 based on:
    # https://twitter.com/xopmine/status/1653790502024560641
    sunrise=(
        ColorSection(MinecraftColor.BLUE, 1),
        ColorSection(MinecraftColor.DARK_AQUA, 2),
        ColorSection(MinecraftColor.GOLD, 1),
    ),
    eclipse=(
        ColorSection(MinecraftColor.DARK_RED, 1),
        ColorSection(MinecraftColor.GRAY, 2),
        ColorSection(MinecraftColor.DARK_RED, 1),
    ),
    gamma=(
        ColorSection(MinecraftColor.BLUE, 2),
        ColorSection(MinecraftColor.LIGHT_PURPLE, 1),
        ColorSection(MinecraftColor.RED, 1),
    ),
    majestic=(
        ColorSection(MinecraftColor.GREEN, 1),
        ColorSection(MinecraftColor.LIGHT_PURPLE, 2),
        ColorSection(MinecraftColor.DARK_PURPLE, 1),
    ),
    andesine=(
        ColorSection(MinecraftColor.RED, 1),
        ColorSection(MinecraftColor.DARK_RED, 2),
        ColorSection(MinecraftColor.DARK_GREEN, 1),
    ),
    marine=(
        ColorSection(MinecraftColor.GREEN, 2),
        ColorSection(MinecraftColor.AQUA, 1),
        ColorSection(MinecraftColor.BLUE, 1),
    ),
    element=(
        ColorSection(MinecraftColor.DARK_RED, 1),
        ColorSection(MinecraftColor.RED, 2),
        ColorSection(MinecraftColor.AQUA, 1),
    ),
    galaxy=(
        ColorSection(MinecraftColor.DARK_BLUE, 1),
        ColorSection(MinecraftColor.BLUE, 1),
        ColorSection(MinecraftColor.DARK_PURPLE, 2),
    ),
    atomic=(
        ColorSection(MinecraftColor.RED, 1),
        ColorSection(MinecraftColor.GREEN, 2),
        ColorSection(MinecraftColor.DARK_AQUA, 1),
    ),
    sunset=(
        ColorSection(MinecraftColor.DARK_PURPLE, 1),
        ColorSection(MinecraftColor.RED, 2),
        ColorSection(MinecraftColor.GOLD, 1),
    ),
    time=(
        ColorSection(MinecraftColor.YELLOW, 1),
        ColorSection(MinecraftColor.GOLD, 1),
        ColorSection(MinecraftColor.RED, 1),
        ColorSection(MinecraftColor.LIGHT_PURPLE, 1),
    ),
    winter=(
        ColorSection(MinecraftColor.BLUE, 1),
        ColorSection(MinecraftColor.DARK_AQUA, 1),
        ColorSection(MinecraftColor.AQUA, 1),
        ColorSection(MinecraftColor.WHITE, 1),
    ),
    obsidian=(
        ColorSection(MinecraftColor.DARK_PURPLE, 1),
        ColorSection(MinecraftColor.DARK_GRAY, 2),
        ColorSection(MinecraftColor.DARK_PURPLE, 1),
    ),
    spring=(
        ColorSection(MinecraftColor.DARK_GREEN, 1),
        ColorSection(MinecraftColor.GREEN, 1),
        ColorSection(MinecraftColor.YELLOW, 1),
        ColorSection(MinecraftColor.GOLD, 1),
    ),
    ice=(
        ColorSection(MinecraftColor.WHITE, 1),
        ColorSection(MinecraftColor.AQUA, 2),
        ColorSection(MinecraftColor.DARK_AQUA, 1),
    ),
    summer=(
        ColorSection(MinecraftColor.AQUA, 1),
        ColorSection(MinecraftColor.YELLOW, 2),
        ColorSection(MinecraftColor.GOLD, 1),
    ),
    spinel=(
        ColorSection(MinecraftColor.DARK_RED, 1),
        ColorSection(MinecraftColor.RED, 2),
        ColorSection(MinecraftColor.BLUE, 1),
    ),
    autumn=(
        ColorSection(MinecraftColor.DARK_PURPLE, 1),
        ColorSection(MinecraftColor.RED, 1),
        ColorSection(MinecraftColor.GOLD, 1),
        ColorSection(MinecraftColor.YELLOW, 1),
    ),
    mystic=(
        ColorSection(MinecraftColor.GREEN, 1),
        ColorSection(MinecraftColor.WHITE, 2),
        ColorSection(MinecraftColor.GREEN, 1),
    ),
    eternal=(
        ColorSection(MinecraftColor.DARK_RED, 1),
        ColorSection(MinecraftColor.DARK_PURPLE, 1),
        ColorSection(MinecraftColor.BLUE, 2),
    ),
)


def make_star_cell_value(text: str, prestige: str) -> CellValue:
    color_sections = PRESTIGE_COLORS[prestige]
    return CellValue(
        text,
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

    text = truncate_float(stars, decimals)
    levels_rating = render_based_on_level(
        text, stars, levels, True, sort_ascending=False
    )
    cell_value_no_star_color = replace(
        cell_value, color_sections=levels_rating.color_sections
    )
    assert (
        render_stars(
            stars, decimals, levels, use_star_colors=False, sort_ascending=False
        )
        == cell_value_no_star_color
    )


USERNAME_VALUE = CellValue.monochrome("username", gui_color=MinecraftColor.LIGHT_PURPLE)
STARS_VALUE = CellValue.monochrome("stars", gui_color=MinecraftColor.DARK_PURPLE)
INDEX_VALUE = CellValue.monochrome("index", gui_color=MinecraftColor.LIGHT_PURPLE)
FKDR_VALUE = CellValue.monochrome("fkdr", gui_color=MinecraftColor.GRAY)
KDR_VALUE = CellValue.monochrome("kdr", gui_color=MinecraftColor.GREEN)
BBLR_VALUE = CellValue.monochrome("bblr", gui_color=MinecraftColor.DARK_GREEN)
WLR_VALUE = CellValue.monochrome("wlr", gui_color=MinecraftColor.AQUA)
WINSTREAK_VALUE = CellValue.monochrome("winstreak", gui_color=MinecraftColor.GREEN)
KILLS_VALUE = CellValue.monochrome("kills", gui_color=MinecraftColor.GOLD)
FINALS_VALUE = CellValue.monochrome("finals", gui_color=MinecraftColor.LIGHT_PURPLE)
BEDS_VALUE = CellValue.monochrome("beds", gui_color=MinecraftColor.RED)
WINS_VALUE = CellValue.monochrome("wins", gui_color=MinecraftColor.AQUA)
SESSIONTIME_VALUE = CellValue.monochrome("sessiontime", gui_color=MinecraftColor.RED)
TAGS_VALUE = CellValue.monochrome("tags", gui_color=MinecraftColor.LIGHT_PURPLE)
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
    sessiontime=SESSIONTIME_VALUE,
    tags=TAGS_VALUE,
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
            SESSIONTIME_VALUE,
            TAGS_VALUE,
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
            CellValue.monochrome("a", GUI_COLORS[0]),
        ),
        (
            "a",
            0,
            False,
            False,
            CellValue.monochrome("a", GUI_COLORS[1]),
        ),
        (
            "a",
            0.1,
            True,
            False,
            CellValue.monochrome("a", GUI_COLORS[1]),
        ),
        (
            "a",
            0.1,
            False,
            False,
            CellValue.monochrome("a", GUI_COLORS[1]),
        ),
        (
            "a",
            0.5,
            True,
            False,
            CellValue.monochrome("a", GUI_COLORS[2]),
        ),
        (
            "a",
            0.5,
            False,
            False,
            CellValue.monochrome("a", GUI_COLORS[1]),
        ),
        (
            "a",
            1,
            True,
            False,
            CellValue.monochrome("a", GUI_COLORS[3]),
        ),
        (
            "a",
            1,
            False,
            False,
            CellValue.monochrome("a", GUI_COLORS[1]),
        ),
        # Ascending
        (
            "a",
            0,
            True,
            True,
            CellValue.monochrome("a", GUI_COLORS[4]),
        ),
        (
            "a",
            0.01,
            True,
            True,
            CellValue.monochrome("a", GUI_COLORS[4]),
        ),
        (
            "a",
            0.1,
            True,
            True,
            CellValue.monochrome("a", GUI_COLORS[4]),
        ),
        (
            "a",
            0.5,
            True,
            True,
            CellValue.monochrome("a", GUI_COLORS[3]),
        ),
        (
            "a",
            0.8,
            True,
            True,
            CellValue.monochrome("a", GUI_COLORS[2]),
        ),
        (
            "a",
            1.0,
            True,
            True,
            CellValue.monochrome("a", GUI_COLORS[2]),
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
    ) == CellValue.monochrome("a", GUI_COLORS[4])


DEFAULT_RATING_CONFIGS = RatingConfigCollection(
    stars=DEFAULT_STARS_CONFIG,
    index=DEFAULT_INDEX_CONFIG,
    fkdr=DEFAULT_FKDR_CONFIG,
    kdr=DEFAULT_KDR_CONFIG,
    bblr=DEFAULT_BBLR_CONFIG,
    wlr=DEFAULT_WLR_CONFIG,
    winstreak=DEFAULT_WINSTREAK_CONFIG,
    kills=DEFAULT_KILLS_CONFIG,
    finals=DEFAULT_FINALS_CONFIG,
    beds=DEFAULT_BEDS_CONFIG,
    wins=DEFAULT_WINS_CONFIG,
    sessiontime=DEFAULT_SESSIONTIME_CONFIG,
)

# Levels are stored in descending order when sorting ascending
STARS_ASCENDING_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(800.0, 500.0, 300.0, 100.0),
    decimals=2,
    sort_ascending=True,
)
STARS_DESCENDING_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(100.0, 300.0, 500.0, 800.0),
    decimals=2,
    sort_ascending=False,
)


@pytest.mark.parametrize(
    "stars_config, index_sort_ascending, stars, gui_color",
    (
        # Sorting ascending -> low stars rated highly
        (STARS_ASCENDING_CONFIG, False, 50, GUI_COLORS[4]),
        (STARS_ASCENDING_CONFIG, False, 1500, GUI_COLORS[0]),
        (STARS_ASCENDING_CONFIG, True, 50, GUI_COLORS[4]),
        (STARS_ASCENDING_CONFIG, True, 1500, GUI_COLORS[0]),
        # Sorting descending -> high stars rated highly
        (STARS_DESCENDING_CONFIG, False, 50, GUI_COLORS[0]),
        (STARS_DESCENDING_CONFIG, False, 1500, GUI_COLORS[4]),
        (STARS_DESCENDING_CONFIG, True, 50, GUI_COLORS[0]),
        (STARS_DESCENDING_CONFIG, True, 1500, GUI_COLORS[4]),
    ),
)
def test_render_stats_stars_uses_stars_sort_ascending(
    stars_config: RatingConfig,
    index_sort_ascending: bool,
    stars: float,
    gui_color: str,
) -> None:
    """The stars cell must be rated by the stars config, not the index config"""
    rating_configs = replace(
        DEFAULT_RATING_CONFIGS,
        stars=stars_config,
        index=replace(DEFAULT_INDEX_CONFIG, sort_ascending=index_sort_ascending),
    )

    stars_cell = render_stats(make_player(stars=stars), rating_configs).stars

    assert stars_cell.color_sections[0].color == gui_color


RATING_COLUMNS = tuple(field.name for field in fields(RatingConfigCollection))

UNIFORM_CONFIG = RatingConfig(
    rate_by_level=True, levels=(1.0, 2.0, 3.0, 4.0), decimals=2, sort_ascending=False
)
UNIFORM_RATING_CONFIGS = RatingConfigCollection(
    **{column: UNIFORM_CONFIG for column in RATING_COLUMNS}
)

# A player scoring above every level in UNIFORM_CONFIG for all stats, so that
# flipping the sort order changes the rating of any column it applies to
HIGH_STAT_PLAYER = make_player(
    stars=1500,
    fkdr=100,
    kdr=100,
    bblr=100,
    wlr=100,
    winstreak=1000,
    kills=1_000_000,
    finals=1_000_000,
    beds=1_000_000,
    wins=1_000_000,
    lastLoginMs=1234567890 - 3_600_000,
    lastLogoutMs=1234567890 - 7_200_000,
)


@pytest.mark.parametrize("column", RATING_COLUMNS)
def test_render_stats_reads_the_config_of_each_column(column: str) -> None:
    """Each rendered cell must depend on its own rating config, and no other"""
    rating_configs = replace(
        UNIFORM_RATING_CONFIGS,
        **{
            column: replace(
                UNIFORM_CONFIG,
                sort_ascending=True,
                levels=tuple(reversed(UNIFORM_CONFIG.levels)),
            )
        },
    )

    before = render_stats(HIGH_STAT_PLAYER, UNIFORM_RATING_CONFIGS)
    after = render_stats(HIGH_STAT_PLAYER, rating_configs)

    changed = {
        field.name
        for field in fields(before)
        if getattr(before, field.name) != getattr(after, field.name)
    }

    assert changed == {column}, f"Flipping the sort order of {column} changed {changed}"
