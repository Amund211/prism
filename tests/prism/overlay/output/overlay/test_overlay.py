import pytest

from prism.overlay.output.cell_renderer import (
    GUI_COLORS,
    TERMINAL_FORMATTINGS,
    RenderedStats,
)
from prism.overlay.output.cells import CellValue, ColorSection
from prism.overlay.output.color import MinecraftColor, TerminalColor
from prism.overlay.output.config import (
    RatingConfigCollection,
    read_rating_config_collection_dict,
)
from prism.overlay.output.overlay.utils import OverlayRowData, player_to_row
from prism.overlay.player import (
    KnownPlayer,
    NickedPlayer,
    PendingPlayer,
    Player,
    Stats,
    UnknownPlayer,
    create_known_player,
)

CURRENT_TIME_MS = 1234567890123
CURRENT_TIME_SECONDS = CURRENT_TIME_MS / 1000

# One minute measured in milliseconds
MINUTE_MS = 60 * 1000
HOUR_MS = 60 * MINUTE_MS
DAY_MS = 24 * HOUR_MS

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
            dataReceivedAtMs=CURRENT_TIME_MS,
            username="Player",
            uuid="some-fake-uuid",
            lastLoginMs=CURRENT_TIME_MS - MINUTE_MS // 2,
            lastLogoutMs=CURRENT_TIME_MS - 2 * DAY_MS,
            stars=10.0,
            stats=Stats(
                index=10.0,
                fkdr=1,
                kdr=0.5,
                bblr=0.5,
                wlr=2.0,
                winstreak=5,
                winstreak_accurate=True,
                kills=10,
                finals=5,
                beds=2,
                wins=1,
            ),
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("Player", *white),
                stars=CellValue("10.00", rating0[0], stone_prestige),
                index=CellValue.monochrome("10", *rating0),
                fkdr=CellValue.monochrome("1", *rating1),
                kdr=CellValue.monochrome("0.50", *rating0),
                bblr=CellValue.monochrome("0.50", *rating1),
                wlr=CellValue.monochrome("2.00", *rating3),
                winstreak=CellValue.monochrome("5", *rating2),
                kills=CellValue.monochrome("10", *rating0),
                finals=CellValue.monochrome("5", *rating0),
                beds=CellValue.monochrome("2", *rating0),
                wins=CellValue.monochrome("1", *rating0),
                sessiontime=CellValue.monochrome("<1m", *rating4),
            ),
        ),
    ),
    (
        KnownPlayer(
            dataReceivedAtMs=CURRENT_TIME_MS,
            username="Denicked",
            nick="the_amazing_nick",
            uuid="some-fake-uuid",
            lastLoginMs=None,
            lastLogoutMs=None,
            stars=600.0,
            stats=Stats(
                index=600.0 * 10.0**2,
                fkdr=10.0,
                kdr=1.2,
                bblr=3.5,
                wlr=2.0,
                winstreak=0,
                winstreak_accurate=True,
                kills=20_000,
                finals=23_000,
                beds=8_000,
                wins=6_000,
            ),
        ),
        (
            "the_amazing_nick",
            RenderedStats(
                username=CellValue.monochrome("Denicked (the_amazing_nick)", *white),
                stars=CellValue("600.00", rating3[0], ruby_prestige),
                index=CellValue.monochrome("60000", *rating4),
                fkdr=CellValue.monochrome("10.00", *rating4),
                kdr=CellValue.monochrome("1.20", *rating1),
                bblr=CellValue.monochrome("3.50", *rating3),
                wlr=CellValue.monochrome("2.00", *rating3),
                winstreak=CellValue.monochrome("0", *rating0),
                kills=CellValue.monochrome("20000", *rating3),
                finals=CellValue.monochrome("23000", *rating3),
                beds=CellValue.monochrome("8000", *rating2),
                wins=CellValue.monochrome("6000", *rating3),
                sessiontime=CellValue.monochrome("-", *rating4),
            ),
        ),
    ),
    (
        NickedPlayer(nick="MrNick"),
        (
            "MrNick",
            RenderedStats(
                username=CellValue.monochrome("MrNick", *white),
                stars=CellValue.monochrome("nick", *rating4),
                index=CellValue.monochrome("nick", *rating4),
                fkdr=CellValue.monochrome("nick", *rating4),
                kdr=CellValue.monochrome("nick", *rating4),
                bblr=CellValue.monochrome("nick", *rating4),
                wlr=CellValue.monochrome("nick", *rating4),
                winstreak=CellValue.monochrome("nick", *rating4),
                kills=CellValue.monochrome("nick", *rating4),
                finals=CellValue.monochrome("nick", *rating4),
                beds=CellValue.monochrome("nick", *rating4),
                wins=CellValue.monochrome("nick", *rating4),
                sessiontime=CellValue.monochrome("nick", *rating4),
            ),
        ),
    ),
    (
        UnknownPlayer("SomeErrorOccurred"),
        (
            "SomeErrorOccurred",  # We allow users to manually denick unknown players
            RenderedStats(
                username=CellValue.monochrome("SomeErrorOccurred", *white),
                stars=CellValue.monochrome("error", *rating4),
                index=CellValue.monochrome("error", *rating4),
                fkdr=CellValue.monochrome("error", *rating4),
                kdr=CellValue.monochrome("error", *rating4),
                bblr=CellValue.monochrome("error", *rating4),
                wlr=CellValue.monochrome("error", *rating4),
                winstreak=CellValue.monochrome("error", *rating4),
                kills=CellValue.monochrome("error", *rating4),
                finals=CellValue.monochrome("error", *rating4),
                beds=CellValue.monochrome("error", *rating4),
                wins=CellValue.monochrome("error", *rating4),
                sessiontime=CellValue.monochrome("error", *rating4),
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
                index=CellValue.monochrome("-", *rating0),
                fkdr=CellValue.monochrome("-", *rating0),
                kdr=CellValue.monochrome("-", *rating0),
                bblr=CellValue.monochrome("-", *rating0),
                wlr=CellValue.monochrome("-", *rating0),
                winstreak=CellValue.monochrome("-", *rating0),
                kills=CellValue.monochrome("-", *rating0),
                finals=CellValue.monochrome("-", *rating0),
                beds=CellValue.monochrome("-", *rating0),
                wins=CellValue.monochrome("-", *rating0),
                sessiontime=CellValue.monochrome("-", *rating0),
            ),
        ),
    ),
    # Missing winstreak and sessiontime
    (
        KnownPlayer(
            dataReceivedAtMs=CURRENT_TIME_MS,
            username="MissingWS",
            uuid="some-fake-uuid",
            lastLoginMs=None,
            lastLogoutMs=CURRENT_TIME_MS - 2 * DAY_MS,
            stars=9.0,
            stats=Stats(
                index=9.0,
                fkdr=1.0,
                kdr=2.1,
                bblr=0.5,
                wlr=2.0,
                winstreak=None,
                winstreak_accurate=False,
                kills=5_100,
                finals=10_100,
                beds=12_000,
                wins=15_000,
            ),
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("MissingWS", *white),
                stars=CellValue("9.00", rating0[0], low_stone_prestige),
                index=CellValue.monochrome("9", *rating0),
                fkdr=CellValue.monochrome("1.00", *rating1),
                kdr=CellValue.monochrome("2.10", *rating3),
                bblr=CellValue.monochrome("0.50", *rating1),
                wlr=CellValue.monochrome("2.00", *rating3),
                winstreak=CellValue.monochrome("-", *rating4),
                kills=CellValue.monochrome("5100", *rating1),
                finals=CellValue.monochrome("10100", *rating2),
                beds=CellValue.monochrome("12000", *rating3),
                wins=CellValue.monochrome("15000", *rating4),
                sessiontime=CellValue.monochrome("-", *rating4),
            ),
        ),
    ),
    (
        KnownPlayer(
            dataReceivedAtMs=CURRENT_TIME_MS,
            username="AccurateMissingWS",
            uuid="some-fake-uuid",
            stars=110.0,
            # Data says player is offline
            lastLoginMs=CURRENT_TIME_MS - 2 * DAY_MS,
            lastLogoutMs=CURRENT_TIME_MS - 2 * DAY_MS + 2 * HOUR_MS,
            stats=Stats(
                index=110.0,
                fkdr=1.0,
                kdr=0.4,
                bblr=0.2,
                wlr=2.0,
                winstreak=None,
                winstreak_accurate=True,
                kills=42_000,
                finals=41_000,
                beds=1900,
                wins=2000,
            ),
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("AccurateMissingWS", *white),
                stars=CellValue("110.00", rating1[0], iron_prestige),
                index=CellValue.monochrome("110", *rating1),
                fkdr=CellValue.monochrome("1.00", *rating1),
                kdr=CellValue.monochrome("0.40", *rating0),
                bblr=CellValue.monochrome("0.20", *rating0),
                wlr=CellValue.monochrome("2.00", *rating3),
                winstreak=CellValue.monochrome("-", *rating4),
                kills=CellValue.monochrome("42000", *rating4),
                finals=CellValue.monochrome("41000", *rating4),
                beds=CellValue.monochrome("1900", *rating0),
                wins=CellValue.monochrome("2000", *rating1),
                sessiontime=CellValue.monochrome("-", *rating4),
            ),
        ),
    ),
    # Inaccurate winstreak
    (
        KnownPlayer(
            dataReceivedAtMs=CURRENT_TIME_MS,
            username="InaccurateWS",
            uuid="some-fake-uuid",
            stars=210.0,
            lastLoginMs=CURRENT_TIME_MS - 2 * DAY_MS,
            lastLogoutMs=None,
            stats=Stats(
                index=210.0,
                fkdr=1.0,
                kdr=1.6,
                bblr=3.2,
                wlr=2.0,
                winstreak=100,
                winstreak_accurate=False,
                kills=6000,
                finals=7000,
                beds=3000,
                wins=4000,
            ),
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("InaccurateWS", *white),
                stars=CellValue("210.00", rating1[0], gold_prestige),
                index=CellValue.monochrome("210", *rating1),
                fkdr=CellValue.monochrome("1.00", *rating1),
                kdr=CellValue.monochrome("1.60", *rating2),
                bblr=CellValue.monochrome("3.20", *rating3),
                wlr=CellValue.monochrome("2.00", *rating3),
                winstreak=CellValue.monochrome("~100", *rating4),
                kills=CellValue.monochrome("6000", *rating1),
                finals=CellValue.monochrome("7000", *rating1),
                beds=CellValue.monochrome("3000", *rating1),
                wins=CellValue.monochrome("4000", *rating2),
                sessiontime=CellValue.monochrome("-", *rating4),
            ),
        ),
    ),
    (
        # Short session time, fresh account
        create_known_player(
            CURRENT_TIME_MS,
            {
                "lastLogin": CURRENT_TIME_MS - 7 * MINUTE_MS,
                "lastLogout": CURRENT_TIME_MS - 2 * DAY_MS,
            },
            "FreshAccount",
            "some-fake-uuid",
            None,
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("FreshAccount", *white),
                stars=CellValue("0.00", rating0[0], low_stone_prestige),
                index=CellValue.monochrome("0", *rating0),
                fkdr=CellValue.monochrome("0", *rating0),
                kdr=CellValue.monochrome("0", *rating0),
                bblr=CellValue.monochrome("0", *rating0),
                wlr=CellValue.monochrome("0", *rating0),
                winstreak=CellValue.monochrome("0", *rating0),
                kills=CellValue.monochrome("0", *rating0),
                finals=CellValue.monochrome("0", *rating0),
                beds=CellValue.monochrome("0", *rating0),
                wins=CellValue.monochrome("0", *rating0),
                sessiontime=CellValue.monochrome("7m", *rating3),
            ),
        ),
    ),
    (
        # Local time is wrong
        create_known_player(
            CURRENT_TIME_MS - 2 * HOUR_MS,
            {
                "lastLogin": CURRENT_TIME_MS - 7 * MINUTE_MS,
                "lastLogout": CURRENT_TIME_MS - 2 * DAY_MS,
            },
            "LocalTimeWrong",
            "some-fake-uuid",
            None,
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("LocalTimeWrong", *white),
                stars=CellValue("0.00", rating0[0], low_stone_prestige),
                index=CellValue.monochrome("0", *rating0),
                fkdr=CellValue.monochrome("0", *rating0),
                kdr=CellValue.monochrome("0", *rating0),
                bblr=CellValue.monochrome("0", *rating0),
                wlr=CellValue.monochrome("0", *rating0),
                winstreak=CellValue.monochrome("0", *rating0),
                kills=CellValue.monochrome("0", *rating0),
                finals=CellValue.monochrome("0", *rating0),
                beds=CellValue.monochrome("0", *rating0),
                wins=CellValue.monochrome("0", *rating0),
                sessiontime=CellValue.monochrome("-", *rating4),
            ),
        ),
    ),
)

test_ids = [player.username for player, row in test_cases]

assert len(test_ids) == len(set(test_ids)), "Test ids should be unique"


# Use the default rating configs
rating_configs = RatingConfigCollection.from_dict(
    read_rating_config_collection_dict({})[0]
)


@pytest.mark.parametrize("player, row", test_cases, ids=test_ids)
def test_stats_to_row(player: Player, row: OverlayRowData) -> None:
    """Assert that player_to_row functions properly"""
    username, stats = player_to_row(player, rating_configs)
    assert username == row[0]
    assert stats == row[1]
