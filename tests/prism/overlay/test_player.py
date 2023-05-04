from typing import Any

import pytest

from prism.calc import bedwars_level_from_exp
from prism.overlay.output.cells import ColumnName
from prism.overlay.player import (
    KnownPlayer,
    Player,
    Stats,
    Winstreaks,
    create_known_player,
    sort_players,
)
from tests.prism.overlay.utils import make_player


def make_winstreaks(
    overall: int | None = 0,
    solo: int | None = 0,
    doubles: int | None = 0,
    threes: int | None = 0,
    fours: int | None = 0,
) -> Winstreaks:
    return Winstreaks(
        overall=overall, solo=solo, doubles=doubles, threes=threes, fours=fours
    )


# A dict of players to choose from
players: dict[str, Player] = {
    "chad": make_player(
        username="chad", stars=100, fkdr=100, wlr=10, winstreak=100, nick="superb_nick"
    ),
    "joe": make_player(username="joe", stars=10, fkdr=10),
    "carl": make_player(username="carl", stars=5, fkdr=1),
    "carl_jr": make_player(username="carl_jr", fkdr=1, wlr=1),
    "carl_jr_jr": make_player(username="carl_jr_jr", fkdr=1, wlr=1, winstreak=10),
    "joseph": make_player(username="joseph", fkdr=1, wlr=2),
    "amazing_nick": make_player(username="amazing_nick", variant="nick"),
    "bad_nick": make_player(username="bad_nick", variant="nick"),
    "maurice": make_player(username="maurice", variant="pending"),
    "alfred": make_player(username="alfred", variant="pending"),
}


@pytest.mark.parametrize(
    "player, winstreaks, winstreaks_accurate, result",
    (
        (
            make_player(),
            make_winstreaks(overall=10),
            True,
            make_player(winstreak=10, winstreak_accurate=True),
        ),
        (
            make_player(winstreak=100, winstreak_accurate=True),
            make_winstreaks(overall=1),
            False,
            make_player(winstreak=100, winstreak_accurate=True),
        ),
    ),
)
def test_update_winstreaks(
    player: KnownPlayer,
    winstreaks: Winstreaks,
    winstreaks_accurate: bool,
    result: KnownPlayer,
) -> None:
    """Assert that player.update_winstreaks functions properly"""
    assert (
        KnownPlayer.update_winstreaks(
            player, **winstreaks, winstreaks_accurate=winstreaks_accurate
        )
        == result
    )


sort_test_cases: tuple[tuple[list[Player], set[str], ColumnName, list[Player]], ...] = (
    # Joe has better fkdr than Carl
    (
        [players["carl"], players["joe"]],
        set(),
        "fkdr",
        [players["joe"], players["carl"]],
    ),
    (
        [players["joe"], players["carl"]],
        set(),
        "fkdr",
        [players["joe"], players["carl"]],
    ),
    # Same fkdr -> sorted by name
    (
        [players["carl_jr"], players["carl"], players["carl_jr_jr"]],
        set(),
        "fkdr",
        [players["carl_jr_jr"], players["carl_jr"], players["carl"]],
    ),
    # If the juniors are on our team though, they get sorted last
    (
        [players["carl_jr"], players["carl"], players["carl_jr_jr"]],
        {"carl_jr_jr"},
        "fkdr",
        [players["carl_jr"], players["carl"], players["carl_jr_jr"]],
    ),
    (
        [players["carl_jr"], players["carl"], players["carl_jr_jr"]],
        {"carl_jr_jr", "carl_jr"},
        "fkdr",
        [players["carl"], players["carl_jr_jr"], players["carl_jr"]],
    ),
    # Everyone has 1 fkdr, so the lobby is sorted by username
    (
        [
            players["carl_jr"],
            players["carl"],
            players["joseph"],
            players["carl_jr_jr"],
        ],
        set(),
        "fkdr",
        [
            players["joseph"],
            players["carl_jr_jr"],
            players["carl_jr"],
            players["carl"],
        ],
    ),
    (
        [
            players["carl_jr"],
            players["carl"],
            players["joseph"],
            players["carl_jr_jr"],
        ],
        {"joseph", "our_username"},
        "fkdr",
        [
            players["carl_jr_jr"],
            players["carl_jr"],
            players["carl"],
            players["joseph"],
        ],
    ),
    # Nicks get sorted at the top - sorted by username descending
    (
        [players["joe"], players["amazing_nick"], players["bad_nick"]],
        set(),
        "fkdr",
        [players["bad_nick"], players["amazing_nick"], players["joe"]],
    ),
    # Pending players get sorted at the bottom (above teammates)
    (
        [players["joe"], players["maurice"], players["alfred"]],
        set(),
        "fkdr",
        [players["joe"], players["maurice"], players["alfred"]],
    ),
    (
        [players["joe"], players["maurice"], players["alfred"]],
        {"joe"},
        "fkdr",
        [players["maurice"], players["alfred"], players["joe"]],
    ),
    (
        [players["joe"], players["maurice"], players["alfred"]],
        {"joe", "maurice"},
        "fkdr",
        [players["alfred"], players["joe"], players["maurice"]],
    ),
    # Both pending players and nicks and real players
    (
        [
            players["carl"],
            players["joe"],
            players["maurice"],
            players["alfred"],
            players["amazing_nick"],
            players["bad_nick"],
        ],
        set(),
        "fkdr",
        [
            players["bad_nick"],
            players["amazing_nick"],
            players["joe"],
            players["carl"],
            players["maurice"],
            players["alfred"],
        ],
    ),
    # Denicked player
    (
        [players["chad"], players["joe"]],
        set(),
        "fkdr",
        [players["chad"], players["joe"]],
    ),
    (
        [players["chad"], players["joe"]],
        {"chad"},
        "fkdr",
        [players["joe"], players["chad"]],
    ),
    # Empty list is ok
    ([], set(), "fkdr", []),
    ([], {"unknown"}, "fkdr", []),
    ([], {"unknown", "unknown2"}, "fkdr", []),
    # Single person is ok
    ([players["joe"]], set(), "fkdr", [players["joe"]]),
    ([players["joe"]], {"unknown", "unknown2"}, "fkdr", [players["joe"]]),
    # Different stats
    (
        [players["joe"], players["chad"], players["carl"], players["carl_jr_jr"]],
        set(),
        "username",
        [players["joe"], players["chad"], players["carl_jr_jr"], players["carl"]],
    ),
    (
        [players["joe"], players["chad"], players["carl"], players["carl_jr_jr"]],
        set(),
        "stars",
        [players["chad"], players["joe"], players["carl"], players["carl_jr_jr"]],
    ),
    (
        [players["joe"], players["chad"], players["carl"], players["carl_jr_jr"]],
        set(),
        "wlr",
        [players["chad"], players["carl_jr_jr"], players["joe"], players["carl"]],
    ),
    (
        [players["joe"], players["chad"], players["carl"], players["carl_jr_jr"]],
        set(),
        "winstreak",
        [players["joe"], players["carl"], players["chad"], players["carl_jr_jr"]],
    ),
)


@pytest.mark.parametrize("players, party_members, column, result", sort_test_cases)
def test_sort_stats(
    players: list[Player],
    party_members: set[str],
    column: ColumnName,
    result: list[Player],
) -> None:
    """Assert that sort_players functions properly"""
    assert sort_players(players, party_members, column) == result


@pytest.mark.parametrize(
    "player, is_missing_winstreaks",
    (
        (make_player(), True),
        (make_player(winstreak=100, winstreak_accurate=False), False),
        (make_player(winstreak=100, winstreak_accurate=True), False),
    ),
)
def test_is_missing_winstreaks(
    player: KnownPlayer, is_missing_winstreaks: bool
) -> None:
    assert player.is_missing_winstreaks == is_missing_winstreaks


@pytest.mark.parametrize(
    "player, aliases",
    (
        (make_player(variant="player", username="player1"), ("player1",)),
        (
            make_player(variant="player", username="player2", nick="AmazingNick"),
            ("player2", "AmazingNick"),
        ),
        (make_player(variant="nick", username="AmazingNick"), ("AmazingNick",)),
        (make_player(variant="pending", username="player3"), ("player3",)),
    ),
)
def test_aliases(player: Player, aliases: tuple[str, ...]) -> None:
    assert player.aliases == aliases


def test_create_known_player(technoblade_playerdata: dict[str, Any]) -> None:
    target = KnownPlayer(
        username="Technoblade",
        uuid="b876ec32e396476ba1158438d83c67d4",
        stars=bedwars_level_from_exp(1076936),
        stats=Stats(
            fkdr=20124 / 260,
            wlr=4924 / (5184 - 4924),
            winstreak=None,
            winstreak_accurate=False,
        ),
    )

    result = create_known_player(
        playerdata=technoblade_playerdata,
        username="Technoblade",
        uuid="b876ec32e396476ba1158438d83c67d4",
        nick=None,
    )

    assert result == target
