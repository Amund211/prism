import unittest.mock
from typing import Any, cast

import pytest

from prism.hypixel import create_known_player
from prism.overlay.output.cell_renderer import (
    RenderedStats,
)
from prism.overlay.output.cells import GUI_COLORS, CellValue, ColorSection
from prism.overlay.output.color import MinecraftColor
from prism.overlay.output.config import (
    RatingConfigCollection,
    read_rating_config_collection_dict,
)
from prism.overlay.output.overlay.overlay_window import OverlayWindow
from prism.overlay.output.overlay.stats_overlay import StatsOverlay
from prism.overlay.output.overlay.utils import (
    OverlayRowData,
    player_to_row,
    with_team_color,
)
from prism.overlay.team_types import (
    TEAM_MINECRAFT_COLORS,
    TEAM_SHORT_LABELS,
    TeamColor,
    TeamDangerBannerData,
)
from prism.overlay.visibility import Hidden, Shown
from prism.player import (
    KnownPlayer,
    NickedPlayer,
    PendingPlayer,
    Player,
    Stats,
    Tags,
    UnknownPlayer,
)
from tests.prism.overlay.utils import create_controller, create_state

CURRENT_TIME_MS = 1234567890123
CURRENT_TIME_SECONDS = CURRENT_TIME_MS / 1000

# One minute measured in milliseconds
MINUTE_MS = 60 * 1000
HOUR_MS = 60 * MINUTE_MS
DAY_MS = 24 * HOUR_MS

rating0, rating1, rating2, rating3, rating4 = GUI_COLORS

white = MinecraftColor.WHITE

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
            tags=Tags(sniping="medium", cheating="high"),
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("Player", white),
                stars=CellValue("10.00", stone_prestige),
                index=CellValue.monochrome("10", rating0),
                fkdr=CellValue.monochrome("1", rating1),
                kdr=CellValue.monochrome("0.50", rating0),
                bblr=CellValue.monochrome("0.50", rating1),
                wlr=CellValue.monochrome("2.00", rating3),
                winstreak=CellValue.monochrome("5", rating2),
                kills=CellValue.monochrome("10", rating0),
                finals=CellValue.monochrome("5", rating0),
                beds=CellValue.monochrome("2", rating0),
                wins=CellValue.monochrome("1", rating0),
                sessiontime=CellValue.monochrome("<1m", rating4),
                tags=CellValue(
                    text="C S",
                    color_sections=(
                        ColorSection(rating4, 1),  # Cheating: high
                        ColorSection(GUI_COLORS[0], 1),  # Space
                        ColorSection(rating3, 1),  # Sniping: medium
                    ),
                ),
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
            tags=Tags(sniping="high", cheating="none"),
        ),
        (
            "the_amazing_nick",
            RenderedStats(
                username=CellValue.monochrome("Denicked (the_amazing_nick)", white),
                stars=CellValue("600.00", ruby_prestige),
                index=CellValue.monochrome("60000", rating4),
                fkdr=CellValue.monochrome("10.00", rating4),
                kdr=CellValue.monochrome("1.20", rating1),
                bblr=CellValue.monochrome("3.50", rating3),
                wlr=CellValue.monochrome("2.00", rating3),
                winstreak=CellValue.monochrome("0", rating0),
                kills=CellValue.monochrome("20000", rating3),
                finals=CellValue.monochrome("23000", rating3),
                beds=CellValue.monochrome("8000", rating2),
                wins=CellValue.monochrome("6000", rating3),
                sessiontime=CellValue.monochrome("-", rating4),
                tags=CellValue(text="S", color_sections=(ColorSection(rating4, 1),)),
            ),
        ),
    ),
    (
        NickedPlayer(nick="MrNick"),
        (
            "MrNick",
            RenderedStats(
                username=CellValue.monochrome("MrNick", white),
                stars=CellValue.monochrome("nick", rating4),
                index=CellValue.monochrome("nick", rating4),
                fkdr=CellValue.monochrome("nick", rating4),
                kdr=CellValue.monochrome("nick", rating4),
                bblr=CellValue.monochrome("nick", rating4),
                wlr=CellValue.monochrome("nick", rating4),
                winstreak=CellValue.monochrome("nick", rating4),
                kills=CellValue.monochrome("nick", rating4),
                finals=CellValue.monochrome("nick", rating4),
                beds=CellValue.monochrome("nick", rating4),
                wins=CellValue.monochrome("nick", rating4),
                sessiontime=CellValue.monochrome("nick", rating4),
                tags=CellValue.monochrome("nick", rating4),
            ),
        ),
    ),
    (
        UnknownPlayer("SomeErrorOccurred"),
        (
            "SomeErrorOccurred",  # We allow users to manually denick unknown players
            RenderedStats(
                username=CellValue.monochrome("SomeErrorOccurred", white),
                stars=CellValue.monochrome("error", rating4),
                index=CellValue.monochrome("error", rating4),
                fkdr=CellValue.monochrome("error", rating4),
                kdr=CellValue.monochrome("error", rating4),
                bblr=CellValue.monochrome("error", rating4),
                wlr=CellValue.monochrome("error", rating4),
                winstreak=CellValue.monochrome("error", rating4),
                kills=CellValue.monochrome("error", rating4),
                finals=CellValue.monochrome("error", rating4),
                beds=CellValue.monochrome("error", rating4),
                wins=CellValue.monochrome("error", rating4),
                sessiontime=CellValue.monochrome("error", rating4),
                tags=CellValue.monochrome("error", rating4),
            ),
        ),
    ),
    (
        PendingPlayer(username="MrPending"),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("MrPending", white),
                stars=CellValue.monochrome("-", rating0),
                index=CellValue.monochrome("-", rating0),
                fkdr=CellValue.monochrome("-", rating0),
                kdr=CellValue.monochrome("-", rating0),
                bblr=CellValue.monochrome("-", rating0),
                wlr=CellValue.monochrome("-", rating0),
                winstreak=CellValue.monochrome("-", rating0),
                kills=CellValue.monochrome("-", rating0),
                finals=CellValue.monochrome("-", rating0),
                beds=CellValue.monochrome("-", rating0),
                wins=CellValue.monochrome("-", rating0),
                sessiontime=CellValue.monochrome("-", rating0),
                tags=CellValue.monochrome("-", rating0),
            ),
        ),
    ),
    # Missing winstreak, sessiontime, and tags
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
            tags=None,  # Request failed or still in flight
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("MissingWS", white),
                stars=CellValue("9.00", low_stone_prestige),
                index=CellValue.monochrome("9", rating0),
                fkdr=CellValue.monochrome("1.00", rating1),
                kdr=CellValue.monochrome("2.10", rating3),
                bblr=CellValue.monochrome("0.50", rating1),
                wlr=CellValue.monochrome("2.00", rating3),
                winstreak=CellValue.monochrome("-", rating4),
                kills=CellValue.monochrome("5100", rating1),
                finals=CellValue.monochrome("10100", rating2),
                beds=CellValue.monochrome("12000", rating3),
                wins=CellValue.monochrome("15000", rating4),
                sessiontime=CellValue.monochrome("-", rating4),
                tags=CellValue.monochrome("-", rating0),
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
            tags=Tags(sniping="none", cheating="high"),
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("AccurateMissingWS", white),
                stars=CellValue("110.00", iron_prestige),
                index=CellValue.monochrome("110", rating1),
                fkdr=CellValue.monochrome("1.00", rating1),
                kdr=CellValue.monochrome("0.40", rating0),
                bblr=CellValue.monochrome("0.20", rating0),
                wlr=CellValue.monochrome("2.00", rating3),
                winstreak=CellValue.monochrome("-", rating4),
                kills=CellValue.monochrome("42000", rating4),
                finals=CellValue.monochrome("41000", rating4),
                beds=CellValue.monochrome("1900", rating0),
                wins=CellValue.monochrome("2000", rating1),
                sessiontime=CellValue.monochrome("-", rating4),
                tags=CellValue(text="C", color_sections=(ColorSection(rating4, 1),)),
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
            tags=Tags(sniping="none", cheating="none"),
        ),
        (
            None,
            RenderedStats(
                username=CellValue.monochrome("InaccurateWS", white),
                stars=CellValue("210.00", gold_prestige),
                index=CellValue.monochrome("210", rating1),
                fkdr=CellValue.monochrome("1.00", rating1),
                kdr=CellValue.monochrome("1.60", rating2),
                bblr=CellValue.monochrome("3.20", rating3),
                wlr=CellValue.monochrome("2.00", rating3),
                winstreak=CellValue.monochrome("~100", rating4),
                kills=CellValue.monochrome("6000", rating1),
                finals=CellValue.monochrome("7000", rating1),
                beds=CellValue.monochrome("3000", rating1),
                wins=CellValue.monochrome("4000", rating2),
                sessiontime=CellValue.monochrome("-", rating4),
                tags=CellValue.monochrome("", rating0),
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
                username=CellValue.monochrome("FreshAccount", white),
                stars=CellValue("0.00", low_stone_prestige),
                index=CellValue.monochrome("0", rating0),
                fkdr=CellValue.monochrome("0", rating0),
                kdr=CellValue.monochrome("0", rating0),
                bblr=CellValue.monochrome("0", rating0),
                wlr=CellValue.monochrome("0", rating0),
                winstreak=CellValue.monochrome("0", rating0),
                kills=CellValue.monochrome("0", rating0),
                finals=CellValue.monochrome("0", rating0),
                beds=CellValue.monochrome("0", rating0),
                wins=CellValue.monochrome("0", rating0),
                sessiontime=CellValue.monochrome("7m", rating3),
                tags=CellValue.monochrome("-", rating0),
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
                username=CellValue.monochrome("LocalTimeWrong", white),
                stars=CellValue("0.00", low_stone_prestige),
                index=CellValue.monochrome("0", rating0),
                fkdr=CellValue.monochrome("0", rating0),
                kdr=CellValue.monochrome("0", rating0),
                bblr=CellValue.monochrome("0", rating0),
                wlr=CellValue.monochrome("0", rating0),
                winstreak=CellValue.monochrome("0", rating0),
                kills=CellValue.monochrome("0", rating0),
                finals=CellValue.monochrome("0", rating0),
                beds=CellValue.monochrome("0", rating0),
                wins=CellValue.monochrome("0", rating0),
                sessiontime=CellValue.monochrome("-", rating4),
                tags=CellValue.monochrome("-", rating0),
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


def test_with_team_color_none() -> None:
    player = test_cases[0][0]
    row = player_to_row(player, rating_configs)
    assert with_team_color(row, None) is row


@pytest.mark.parametrize("team", ("red", "blue", "green", "yellow"))
def test_with_team_color_teams(team: TeamColor) -> None:
    player = test_cases[0][0]
    row = player_to_row(player, rating_configs)
    colored_row = with_team_color(row, team)
    nick, stats = colored_row
    assert nick == row[0]
    prefix = f"[{TEAM_SHORT_LABELS[team]}] "
    assert stats.username.text == f"{prefix}{row[1].username.text}"
    assert stats.username.color_sections[0] == ColorSection(
        TEAM_MINECRAFT_COLORS[team], len(prefix)
    )
    assert stats.username.color_sections[1:] == row[1].username.color_sections


class MockOverlayWindow:
    def __init__(self, shown: bool = True) -> None:
        self.shown = shown
        self.root = unittest.mock.MagicMock()

    def show(self) -> None:
        self.shown = True

    def hide(self) -> None:
        self.shown = False

    def schedule_hide(self, timeout_ms: int) -> None:
        pass

    def schedule_hide_at(self, deadline: float) -> None:
        pass


def test_stats_overlay_hidden_caching_and_flush() -> None:
    """Test that updates while hidden are cached and flushed when shown."""
    mock_main_content = unittest.mock.MagicMock()
    mock_window = MockOverlayWindow(shown=False)

    overlay = StatsOverlay.__new__(StatsOverlay)
    overlay.controller = create_controller()
    overlay.poll_interval = 100
    overlay.visibility = Hidden()
    overlay.last_new_rows = None
    overlay.last_new_banner = None
    overlay.current_page = "main"
    overlay.tab_pressed = False
    overlay.window = cast(OverlayWindow, mock_window)
    overlay.main_content = mock_main_content
    overlay.rush_popup = unittest.mock.MagicMock()
    overlay.rush_popup_controller = unittest.mock.MagicMock()
    overlay.rush_popup_controller.tick.return_value = None

    test_row = player_to_row(test_cases[0][0], rating_configs)
    test_banner = TeamDangerBannerData(
        headline=CellValue.monochrome("Test Banner", "gray60"),
        team_summary_line=None,
    )

    # Tick 1: Hidden, data arrives -> cached, update_content not called
    overlay.get_new_data = lambda: (Hidden(), [], [test_row], test_banner)
    overlay.update_overlay()

    mock_main_content.update_content.assert_not_called()
    assert overlay.last_new_rows == [test_row]
    assert overlay.last_new_banner == test_banner

    # Tick 2: Shown (e.g. Tab pressed), no new data -> flushes cached rows & banner
    mock_window.shown = True
    overlay.get_new_data = lambda: (Shown(), [], None, None)
    overlay.update_overlay()

    mock_main_content.update_content.assert_called_once_with(
        [], [test_row], test_banner
    )
    assert overlay.last_new_rows is None
    assert overlay.last_new_banner is None

    # Tick 3: Shown, new data arrives -> passed directly, not cached
    mock_main_content.update_content.reset_mock()
    test_banner_2 = TeamDangerBannerData(
        headline=CellValue.monochrome("Banner 2", "snow"),
        team_summary_line=None,
    )
    overlay.get_new_data = lambda: (Shown(), [], [test_row], test_banner_2)
    overlay.update_overlay()

    mock_main_content.update_content.assert_called_once_with(
        [], [test_row], test_banner_2
    )
    assert overlay.last_new_rows is None
    assert overlay.last_new_banner is None


def test_stats_overlay_page_not_main_caching() -> None:
    """Test that updates when current_page != 'main' are cached until back on main."""
    mock_main_content = unittest.mock.MagicMock()
    mock_window = MockOverlayWindow(shown=True)

    overlay = StatsOverlay.__new__(StatsOverlay)
    overlay.controller = create_controller()
    overlay.poll_interval = 100
    overlay.visibility = Shown()
    overlay.last_new_rows = None
    overlay.last_new_banner = None
    overlay.current_page = "settings"
    overlay.settings_page = unittest.mock.MagicMock()
    overlay.tab_pressed = False
    overlay.window = cast(OverlayWindow, mock_window)
    overlay.main_content = mock_main_content
    overlay.rush_popup = unittest.mock.MagicMock()
    overlay.rush_popup_controller = unittest.mock.MagicMock()
    overlay.rush_popup_controller.tick.return_value = None

    test_row = player_to_row(test_cases[0][0], rating_configs)
    test_banner = TeamDangerBannerData(
        headline=CellValue.monochrome("Test Banner", "gray60"),
        team_summary_line=None,
    )

    overlay.get_new_data = lambda: (Shown(), [], [test_row], test_banner)
    overlay.update_overlay()

    # In settings page, update_content should NOT be called on main_content
    mock_main_content.update_content.assert_not_called()
    assert overlay.last_new_rows == [test_row]
    assert overlay.last_new_banner == test_banner


def test_stats_overlay_init_initializes_rush_popup() -> None:
    controller = create_controller()
    microsoft_account = unittest.mock.MagicMock()

    with (
        unittest.mock.patch("prism.overlay.output.overlay.stats_overlay.OverlayWindow"),
        unittest.mock.patch("prism.overlay.output.overlay.stats_overlay.MainContent"),
        unittest.mock.patch("prism.overlay.output.overlay.stats_overlay.SettingsPage"),
        unittest.mock.patch(
            "prism.overlay.output.overlay.stats_overlay.SetNicknamePage"
        ),
        unittest.mock.patch("prism.overlay.output.overlay.stats_overlay.Toolbar"),
        unittest.mock.patch(
            "prism.overlay.output.overlay.stats_overlay.RushPopup"
        ) as mock_rush_popup_cls,
        unittest.mock.patch(
            "prism.overlay.output.overlay.stats_overlay.RushPopupController.create"
        ) as mock_rush_controller_create,
    ):
        overlay = StatsOverlay(
            start_hidden=True,
            column_order=("username", "stars"),
            controller=controller,
            microsoft_account=microsoft_account,
            get_new_data=lambda: (Hidden(), [], None, None),
            poll_interval=100,
        )

        mock_rush_popup_cls.assert_called_once_with(overlay.window.root)
        mock_rush_controller_create.assert_called_once_with(timeout_seconds=10.0)
        assert overlay.rush_popup == mock_rush_popup_cls.return_value
        assert overlay.rush_popup_controller == mock_rush_controller_create.return_value


def test_stats_overlay_rush_popup_tick() -> None:
    mock_window = MockOverlayWindow(shown=False)
    mock_popup = unittest.mock.MagicMock()
    mock_popup_controller = unittest.mock.MagicMock()

    controller = create_controller(
        state=create_state(
            lobby_players={"Player1", "Player2"},
            in_queue=True,
            who_counter=3,
        )
    )

    overlay = StatsOverlay.__new__(StatsOverlay)
    overlay.controller = controller
    overlay.poll_interval = 100
    overlay.visibility = Hidden()
    overlay.last_new_rows = None
    overlay.last_new_banner = None
    overlay.current_page = "main"
    overlay.tab_pressed = False
    overlay.window = cast(OverlayWindow, mock_window)
    overlay.main_content = unittest.mock.MagicMock()
    overlay.rush_popup = mock_popup
    overlay.rush_popup_controller = mock_popup_controller

    test_banner = TeamDangerBannerData(
        headline=CellValue.monochrome("Target: Red", "snow"),
        team_summary_line=None,
    )

    # When controller.tick returns a banner -> popup.tick(banner) is called
    mock_popup_controller.tick.return_value = test_banner
    overlay.get_new_data = lambda: (Hidden(), [], None, test_banner)
    overlay.update_overlay()

    mock_popup_controller.tick.assert_called_once()
    _, kwargs = mock_popup_controller.tick.call_args
    assert kwargs["who_counter"] == 3
    assert kwargs["in_lobby_or_game"] is True
    assert kwargs["banner"] == test_banner
    assert isinstance(kwargs["now"], float)
    mock_popup.tick.assert_called_once_with(test_banner)
    mock_popup.hide.assert_not_called()

    # When controller.tick returns None -> popup.hide() is called
    mock_popup.reset_mock()
    mock_popup_controller.reset_mock()
    mock_popup_controller.tick.return_value = None

    overlay.get_new_data = lambda: (Hidden(), [], None, None)
    overlay.update_overlay()

    mock_popup.hide.assert_called_once()
    mock_popup.tick.assert_not_called()


@pytest.mark.parametrize(
    "lobby_players, in_queue, in_game, duel, expected_in_lobby_or_game",
    [
        (set(), True, False, None, False),
        ({"Player1"}, False, False, None, False),
        ({"Player1"}, True, False, "rush", False),
        ({"Player1"}, True, False, None, True),
        ({"Player1"}, False, True, None, True),
    ],
)
def test_stats_overlay_in_lobby_or_game_calculation(
    lobby_players: set[str],
    in_queue: bool,
    in_game: bool,
    duel: str | None,
    expected_in_lobby_or_game: bool,
) -> None:
    mock_window = MockOverlayWindow(shown=False)
    mock_popup = unittest.mock.MagicMock()
    mock_popup_controller = unittest.mock.MagicMock()
    mock_popup_controller.tick.return_value = None

    controller = create_controller(
        state=create_state(
            lobby_players=lobby_players,
            in_queue=in_queue,
            last_game_start=100.0 if in_game else None,
            bedwars_duel=cast(Any, duel),
        )
    )

    overlay = StatsOverlay.__new__(StatsOverlay)
    overlay.controller = controller
    overlay.poll_interval = 100
    overlay.visibility = Hidden()
    overlay.last_new_rows = None
    overlay.last_new_banner = None
    overlay.current_page = "main"
    overlay.tab_pressed = False
    overlay.window = cast(OverlayWindow, mock_window)
    overlay.main_content = unittest.mock.MagicMock()
    overlay.rush_popup = mock_popup
    overlay.rush_popup_controller = mock_popup_controller

    overlay.get_new_data = lambda: (Hidden(), [], None, None)
    overlay.update_overlay()

    mock_popup_controller.tick.assert_called_once()
    _, kwargs = mock_popup_controller.tick.call_args
    assert kwargs["in_lobby_or_game"] is expected_in_lobby_or_game
