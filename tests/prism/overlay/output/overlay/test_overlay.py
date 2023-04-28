import pytest

from prism.overlay.output.cell_renderer import (
    GUI_COLORS,
    TERMINAL_FORMATTINGS,
    RenderedStats,
)
from prism.overlay.output.cells import CellValue, ColorSection
from prism.overlay.output.color import MinecraftColor, TerminalColor
from prism.overlay.output.config import (
    FKDR_LEVELS,
    STARS_LEVELS,
    WINSTREAK_LEVELS,
    WLR_LEVELS,
    RatingConfig,
    RatingConfigCollection,
)
from prism.overlay.output.overlay.utils import OverlayRowData, player_to_row
from prism.overlay.player import KnownPlayer, NickedPlayer, PendingPlayer, Player, Stats

# Tuples (terminal_formatting, gui_color)
rating0, rating1, rating2, rating3, rating4 = zip(TERMINAL_FORMATTINGS, GUI_COLORS)

white = (TerminalColor.LIGHT_WHITE, MinecraftColor.WHITE)

low_stone_prestige = (
    ColorSection(MinecraftColor.GRAY, 1),
    ColorSection(MinecraftColor.GRAY, -1),
)
stone_prestige = (
    ColorSection(MinecraftColor.GRAY, 2),
    ColorSection(MinecraftColor.GRAY, -1),
)
iron_prestige = (
    ColorSection(MinecraftColor.WHITE, 3),
    ColorSection(MinecraftColor.GRAY, -1),
)
gold_prestige = (
    ColorSection(MinecraftColor.GOLD, 3),
    ColorSection(MinecraftColor.GRAY, -1),
)
ruby_prestige = (
    ColorSection(MinecraftColor.DARK_RED, 3),
    ColorSection(MinecraftColor.GRAY, -1),
)

test_cases: tuple[tuple[Player, OverlayRowData], ...] = (
    (
        KnownPlayer(
            username="Player",
            uuid="some-fake-uuid",
            stars=10.0,
            stats=Stats(
                fkdr=1,
                wlr=2.0,
                winstreak=15,
                winstreak_accurate=True,
            ),
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("Player", *white),
                stars=CellValue("10.00", rating0[0], stone_prestige),
                fkdr=CellValue.monochrome("1", *rating1),
                wlr=CellValue.monochrome("2.00", *rating3),
                winstreak=CellValue.monochrome("15", *rating2),
            ),
        ),
    ),
    (
        KnownPlayer(
            username="Denicked",
            nick="the_amazing_nick",
            uuid="some-fake-uuid",
            stars=600.0,
            stats=Stats(
                fkdr=10.0,
                wlr=2.0,
                winstreak=0,
                winstreak_accurate=True,
            ),
        ),
        (
            "the_amazing_nick",
            RenderedStats(
                username=CellValue.monochrome("Denicked (the_amazing_nick)", *white),
                stars=CellValue("600.00", rating3[0], ruby_prestige),
                fkdr=CellValue.monochrome("10.00", *rating4),
                wlr=CellValue.monochrome("2.00", *rating3),
                winstreak=CellValue.monochrome("0", *rating0),
            ),
        ),
    ),
    (
        NickedPlayer(nick="MrNick"),
        (
            "MrNick",
            RenderedStats(
                username=CellValue.monochrome("MrNick", *white),
                stars=CellValue.monochrome("unknown", *rating4),
                fkdr=CellValue.monochrome("unknown", *rating4),
                wlr=CellValue.monochrome("unknown", *rating4),
                winstreak=CellValue.monochrome("unknown", *rating4),
            ),
        ),
    ),
    (
        PendingPlayer(username="MrPending"),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("MrPending", *white),
                stars=CellValue.monochrome("-", *rating0),
                fkdr=CellValue.monochrome("-", *rating0),
                wlr=CellValue.monochrome("-", *rating0),
                winstreak=CellValue.monochrome("-", *rating0),
            ),
        ),
    ),
    # Missing winstreak
    (
        KnownPlayer(
            username="MissingWS",
            uuid="some-fake-uuid",
            stars=9.0,
            stats=Stats(
                fkdr=1.0,
                wlr=2.0,
                winstreak=None,
                winstreak_accurate=False,
            ),
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("MissingWS", *white),
                stars=CellValue("9.00", rating0[0], low_stone_prestige),
                fkdr=CellValue.monochrome("1.00", *rating1),
                wlr=CellValue.monochrome("2.00", *rating3),
                winstreak=CellValue.monochrome("-", *rating0),
            ),
        ),
    ),
    (
        KnownPlayer(
            username="AccurateMissingWS",
            uuid="some-fake-uuid",
            stars=110.0,
            stats=Stats(
                fkdr=1.0,
                wlr=2.0,
                winstreak=None,
                winstreak_accurate=True,
            ),
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("AccurateMissingWS", *white),
                stars=CellValue("110.00", rating1[0], iron_prestige),
                fkdr=CellValue.monochrome("1.00", *rating1),
                wlr=CellValue.monochrome("2.00", *rating3),
                winstreak=CellValue.monochrome("-", *rating0),
            ),
        ),
    ),
    # Inaccurate winstreak
    (
        KnownPlayer(
            username="InaccurateWS",
            uuid="some-fake-uuid",
            stars=210.0,
            stats=Stats(
                fkdr=1.0,
                wlr=2.0,
                winstreak=100,
                winstreak_accurate=False,
            ),
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("InaccurateWS", *white),
                stars=CellValue("210.00", rating1[0], gold_prestige),
                fkdr=CellValue.monochrome("1.00", *rating1),
                wlr=CellValue.monochrome("2.00", *rating3),
                winstreak=CellValue.monochrome("100?", *rating4),
            ),
        ),
    ),
)

test_ids = [player.username for player, row in test_cases]

assert len(test_ids) == len(set(test_ids)), "Test ids should be unique"


rating_configs = RatingConfigCollection(
    stars=RatingConfig(levels=STARS_LEVELS, decimals=2),
    fkdr=RatingConfig(levels=FKDR_LEVELS, decimals=2),
    wlr=RatingConfig(levels=WLR_LEVELS, decimals=2),
    winstreak=RatingConfig(levels=WINSTREAK_LEVELS, decimals=2),
)


@pytest.mark.parametrize("player, row", test_cases, ids=test_ids)
def test_stats_to_row(player: Player, row: OverlayRowData) -> None:
    """Assert that player_to_row functions properly"""
    username, stats = player_to_row(player, rating_configs)
    assert username == row[0]
    assert stats == row[1]
