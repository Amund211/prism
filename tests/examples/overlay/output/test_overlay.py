import pytest

from examples.overlay.output.overlay import DEFAULT_COLOR, LEVEL_COLORMAP, player_to_row
from examples.overlay.output.overlay_window import CellValue, OverlayRow
from examples.overlay.stats import (
    KnownPlayer,
    NickedPlayer,
    Player,
    PropertyName,
    Stats,
)

rating0, rating1, rating2, rating3, rating4 = LEVEL_COLORMAP

test_cases = (
    (
        KnownPlayer(
            username="Player1",
            uuid="some-fake-uuid",
            stars=10.0,
            stats=Stats(
                fkdr=1.0,
                wlr=2.0,
                winstreak=15,
                winstreak_accurate=True,
            ),
        ),
        {
            "username": CellValue("Player1", DEFAULT_COLOR),
            "stars": CellValue("10.00", rating0),
            "fkdr": CellValue("1.00", rating1),
            "wlr": CellValue("2.00", rating3),
            "winstreak": CellValue("15", rating2),
        },
    ),
    (
        KnownPlayer(
            username="Player2",
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
        {
            "username": CellValue("Player2 (the_amazing_nick)", DEFAULT_COLOR),
            "stars": CellValue("600.00", rating3),
            "fkdr": CellValue("10.00", rating4),
            "wlr": CellValue("2.00", rating3),
            "winstreak": CellValue("0", rating0),
        },
    ),
    (
        NickedPlayer(nick="Player3"),
        {
            "username": CellValue("Player3", DEFAULT_COLOR),
            "stars": CellValue("unknown", rating4),
            "fkdr": CellValue("unknown", rating4),
            "wlr": CellValue("unknown", rating4),
            "winstreak": CellValue("unknown", rating4),
        },
    ),
    # Missing winstreak
    (
        KnownPlayer(
            username="Player4",
            uuid="some-fake-uuid",
            stars=10.0,
            stats=Stats(
                fkdr=1.0,
                wlr=2.0,
                winstreak=None,
                winstreak_accurate=False,
            ),
        ),
        {
            "username": CellValue("Player4", DEFAULT_COLOR),
            "stars": CellValue("10.00", rating0),
            "fkdr": CellValue("1.00", rating1),
            "wlr": CellValue("2.00", rating3),
            "winstreak": CellValue("-", DEFAULT_COLOR),
        },
    ),
    (
        KnownPlayer(
            username="Player5",
            uuid="some-fake-uuid",
            stars=10.0,
            stats=Stats(
                fkdr=1.0,
                wlr=2.0,
                winstreak=None,
                winstreak_accurate=True,
            ),
        ),
        {
            "username": CellValue("Player5", DEFAULT_COLOR),
            "stars": CellValue("10.00", rating0),
            "fkdr": CellValue("1.00", rating1),
            "wlr": CellValue("2.00", rating3),
            "winstreak": CellValue("-", DEFAULT_COLOR),
        },
    ),
    # Inaccurate winstreak
    (
        KnownPlayer(
            username="Player6",
            uuid="some-fake-uuid",
            stars=10.0,
            stats=Stats(
                fkdr=1.0,
                wlr=2.0,
                winstreak=100,
                winstreak_accurate=False,
            ),
        ),
        {
            "username": CellValue("Player6", DEFAULT_COLOR),
            "stars": CellValue("10.00", rating0),
            "fkdr": CellValue("1.00", rating1),
            "wlr": CellValue("2.00", rating3),
            "winstreak": CellValue("100?", rating4),
        },
    ),
)

test_ids = [player.username for player, row in test_cases]  # type: ignore

assert len(test_ids) == len(set(test_ids)), "Test ids should be unique"


@pytest.mark.parametrize("player, row", test_cases, ids=test_ids)
def test_stats_to_row(player: Player, row: OverlayRow[PropertyName]) -> None:
    """Assert that player_to_row functions properly"""
    assert player_to_row(player) == row
