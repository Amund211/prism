import pytest

from examples.overlay.output.overlay import DEFAULT_COLOR, LEVEL_COLORMAP, stats_to_row
from examples.overlay.output.overlay_window import CellValue, OverlayRow
from examples.overlay.stats import NickedPlayer, PlayerStats, PropertyName, Stats

rating0, rating1, rating2, rating3, rating4 = LEVEL_COLORMAP

test_cases = (
    (
        PlayerStats(username="Player1", stars=10.0, fkdr=1.0, wlr=2.0, winstreak=15),
        {
            "username": CellValue("Player1", DEFAULT_COLOR),
            "stars": CellValue("10.00", rating0),
            "fkdr": CellValue("1.00", rating1),
            "wlr": CellValue("2.00", rating3),
            "winstreak": CellValue("15", rating2),
        },
    ),
    (
        PlayerStats(
            username="Player2",
            nick="the_amazing_nick",
            stars=600.0,
            fkdr=10.0,
            wlr=2.0,
            winstreak=0,
        ),
        {
            "username": CellValue("Player2 (the_amazing_nick)", DEFAULT_COLOR),
            "stars": CellValue("600.00", rating3),
            "fkdr": CellValue("10.00", rating4),
            "wlr": CellValue("2.00", rating3),
            "winstreak": CellValue("0", rating0),
        },
    ),
    (
        NickedPlayer(username="Player3"),
        {
            "username": CellValue("Player3", DEFAULT_COLOR),
            "stars": CellValue("unknown", rating4),
            "fkdr": CellValue("unknown", rating4),
            "wlr": CellValue("unknown", rating4),
            "winstreak": CellValue("unknown", rating4),
        },
    ),
)

test_ids = [stats.username for stats, row in test_cases]  # type: ignore

assert len(test_ids) == len(set(test_ids)), "Test ids should be unique"


@pytest.mark.parametrize("stats, row", test_cases, ids=test_ids)
def test_stats_to_row(stats: Stats, row: OverlayRow[PropertyName]) -> None:
    """Assert that stats_to_row functions properly"""
    assert stats_to_row(stats) == row
