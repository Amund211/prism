import pytest

from examples.sidelay.output.overlay import stats_to_row
from examples.sidelay.output.overlay_window import CellValue, OverlayRow
from examples.sidelay.stats import NickedPlayer, PlayerStats, PropertyName, Stats


# TODO: tests with proper colors, consider number formatting
@pytest.mark.parametrize(
    "stats, row",
    (
        (
            PlayerStats(username="abc", stars=100.0, fkdr=1.0, wlr=2.0, winstreak=15),
            {
                "username": CellValue("abc", "white"),
                "stars": CellValue("100.00", "white"),
                "fkdr": CellValue("1.00", "white"),
                "wlr": CellValue("2.00", "white"),
                "winstreak": CellValue("15", "white"),
            },
        ),
        (
            PlayerStats(
                username="abc",
                nick="the_amazing_nick",
                stars=100.0,
                fkdr=1.0,
                wlr=2.0,
                winstreak=15,
            ),
            {
                "username": CellValue("abc (the_amazing_nick)", "white"),
                "stars": CellValue("100.00", "white"),
                "fkdr": CellValue("1.00", "white"),
                "wlr": CellValue("2.00", "white"),
                "winstreak": CellValue("15", "white"),
            },
        ),
        (
            NickedPlayer(username="abc"),
            {
                "username": CellValue("abc", "white"),
                "stars": CellValue("unknown", "white"),
                "fkdr": CellValue("unknown", "white"),
                "wlr": CellValue("unknown", "white"),
                "winstreak": CellValue("unknown", "white"),
            },
        ),
    ),
)
def test_update_state(stats: Stats, row: OverlayRow[PropertyName]) -> None:
    """Assert that stats_to_row functions properly"""
    assert stats_to_row(stats) == row
