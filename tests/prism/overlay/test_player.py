from collections.abc import Mapping

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
    "error_guy": make_player(username="error_guy", variant="unknown"),
    "jonathan": make_player(
        username="jonathan",
        stars=1,
        fkdr=1,
        kdr=1,
        bblr=1,
        wlr=1,
        winstreak=2,
        kills=2,
        finals=2,
        beds=2,
        wins=2,
        lastLogoutMs=1000,
        lastLoginMs=2000,
    ),
    "nathaniel": make_player(
        username="nathaniel",
        stars=2,
        fkdr=3,
        kdr=3,
        bblr=4,
        wlr=4,
        winstreak=1,
        kills=1,
        finals=3,
        beds=3,
        wins=4,
        lastLogoutMs=2000,
        lastLoginMs=1000,
    ),
    "joshua": make_player(
        username="joshua",
        stars=4,
        fkdr=2.2,
        kdr=4,
        bblr=2,
        wlr=3,
        winstreak=3,
        kills=4,
        finals=1,
        beds=4,
        wins=1,
        lastLogoutMs=3000,
        lastLoginMs=4000,
    ),
    "nigel": make_player(
        username="nigel",
        stars=3,
        fkdr=4,
        kdr=2,
        bblr=3,
        wlr=2,
        winstreak=None,
        kills=3,
        finals=4,
        beds=1,
        wins=3,
        lastLogoutMs=4000,
        lastLoginMs=3000,
    ),
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


sort_test_cases: tuple[
    tuple[list[Player], set[str], ColumnName, list[Player], list[Player] | None], ...
] = (
    # Unknown player sorted to the top
    (
        [players["joshua"], players["error_guy"]],
        set(),
        "fkdr",
        [players["error_guy"], players["joshua"]],
        [players["error_guy"], players["joshua"]],
    ),
    # Joe has better fkdr than Carl
    (
        [players["carl"], players["joe"]],
        set(),
        "fkdr",
        [players["joe"], players["carl"]],
        None,
    ),
    (
        [players["joe"], players["carl"]],
        set(),
        "fkdr",
        [players["joe"], players["carl"]],
        None,
    ),
    # Same fkdr -> sorted by name
    (
        [players["carl_jr"], players["carl"], players["carl_jr_jr"]],
        set(),
        "fkdr",
        [players["carl"], players["carl_jr"], players["carl_jr_jr"]],
        # Ascending sort by fkdr also gives fallback sort by name
        [players["carl"], players["carl_jr"], players["carl_jr_jr"]],
    ),
    # If the juniors are on our team though, they get sorted last
    (
        [players["carl_jr"], players["carl"], players["carl_jr_jr"]],
        {"carl_jr_jr"},
        "fkdr",
        [players["carl"], players["carl_jr"], players["carl_jr_jr"]],
        [players["carl"], players["carl_jr"], players["carl_jr_jr"]],
    ),
    (
        [players["carl_jr"], players["carl"], players["carl_jr_jr"]],
        {"carl_jr_jr", "carl_jr"},
        "fkdr",
        [players["carl"], players["carl_jr"], players["carl_jr_jr"]],
        [players["carl"], players["carl_jr"], players["carl_jr_jr"]],
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
            players["carl"],
            players["carl_jr"],
            players["carl_jr_jr"],
            players["joseph"],
        ],
        [
            players["carl"],
            players["carl_jr"],
            players["carl_jr_jr"],
            players["joseph"],
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
            players["carl"],
            players["carl_jr"],
            players["carl_jr_jr"],
            players["joseph"],
        ],
        [
            players["carl"],
            players["carl_jr"],
            players["carl_jr_jr"],
            players["joseph"],
        ],
    ),
    # Nicks get sorted at the top - sorted by username
    (
        [players["joe"], players["amazing_nick"], players["bad_nick"]],
        set(),
        "fkdr",
        [players["amazing_nick"], players["bad_nick"], players["joe"]],
        [players["amazing_nick"], players["bad_nick"], players["joe"]],
    ),
    # Pending players get sorted at the bottom (above teammates)
    (
        [players["joe"], players["maurice"], players["alfred"]],
        set(),
        "fkdr",
        [players["joe"], players["alfred"], players["maurice"]],
        [players["joe"], players["alfred"], players["maurice"]],
    ),
    (
        [players["joe"], players["maurice"], players["alfred"]],
        {"joe"},
        "fkdr",
        [players["alfred"], players["maurice"], players["joe"]],
        [players["alfred"], players["maurice"], players["joe"]],
    ),
    (
        [players["joe"], players["maurice"], players["alfred"]],
        {"joe", "maurice"},
        "fkdr",
        [players["alfred"], players["joe"], players["maurice"]],
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
            players["amazing_nick"],
            players["bad_nick"],
            players["joe"],
            players["carl"],
            players["alfred"],
            players["maurice"],
        ],
        [
            players["amazing_nick"],
            players["bad_nick"],
            players["carl"],
            players["joe"],
            players["alfred"],
            players["maurice"],
        ],
    ),
    # Denicked player
    (
        [players["chad"], players["joe"]],
        set(),
        "fkdr",
        [players["chad"], players["joe"]],
        None,
    ),
    (
        [players["chad"], players["joe"]],
        {"chad"},
        "fkdr",
        [players["joe"], players["chad"]],
        [players["joe"], players["chad"]],
    ),
    # Empty list is ok
    ([], set(), "fkdr", [], None),
    ([], {"unknown"}, "fkdr", [], None),
    ([], {"unknown", "unknown2"}, "fkdr", [], None),
    # Single person is ok
    ([players["joe"]], set(), "fkdr", [players["joe"]], None),
    ([players["joe"]], {"unknown", "unknown2"}, "fkdr", [players["joe"]], None),
    # Different stats
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "username",
        [
            players["jonathan"],
            players["joshua"],
            players["nathaniel"],
            players["nigel"],
        ],
        # Sort on username is not affected by sort_ascending
        [
            players["jonathan"],
            players["joshua"],
            players["nathaniel"],
            players["nigel"],
        ],
    ),
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "index",
        [
            players["nigel"],
            players["joshua"],
            players["nathaniel"],
            players["jonathan"],
        ],
        None,
    ),
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "stars",
        [
            players["joshua"],
            players["nigel"],
            players["nathaniel"],
            players["jonathan"],
        ],
        None,
    ),
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "fkdr",
        [
            players["nigel"],
            players["nathaniel"],
            players["joshua"],
            players["jonathan"],
        ],
        None,
    ),
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "kdr",
        [
            players["joshua"],
            players["nathaniel"],
            players["nigel"],
            players["jonathan"],
        ],
        None,
    ),
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "bblr",
        [
            players["nathaniel"],
            players["nigel"],
            players["joshua"],
            players["jonathan"],
        ],
        None,
    ),
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "wlr",
        [
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
            players["jonathan"],
        ],
        None,
    ),
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "winstreak",
        [
            players["nigel"],
            players["joshua"],
            players["jonathan"],
            players["nathaniel"],
        ],
        None,
    ),
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "kills",
        [
            players["joshua"],
            players["nigel"],
            players["jonathan"],
            players["nathaniel"],
        ],
        None,
    ),
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "finals",
        [
            players["nigel"],
            players["nathaniel"],
            players["jonathan"],
            players["joshua"],
        ],
        None,
    ),
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "beds",
        [
            players["joshua"],
            players["nathaniel"],
            players["jonathan"],
            players["nigel"],
        ],
        None,
    ),
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "wins",
        [
            players["nathaniel"],
            players["nigel"],
            players["jonathan"],
            players["joshua"],
        ],
        None,
    ),
    (
        [
            players["jonathan"],
            players["nathaniel"],
            players["joshua"],
            players["nigel"],
        ],
        set(),
        "sessiontime",
        [
            players["joshua"],
            players["nigel"],
            players["jonathan"],
            players["nathaniel"],
        ],
        None,
    ),
)


@pytest.mark.parametrize(
    "players, party_members, column, result, ascending_result", sort_test_cases
)
def test_sort_stats(
    players: list[Player],
    party_members: set[str],
    column: ColumnName,
    result: list[Player],
    ascending_result: list[Player] | None,
) -> None:
    """Assert that sort_players functions properly"""
    assert sort_players(players, party_members, column, sort_ascending=False) == result

    ascending_result = (
        ascending_result if ascending_result is not None else list(reversed(result))
    )
    assert sort_players(players, party_members, column, sort_ascending=True) == list(
        ascending_result
    )


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
        (make_player(variant="unknown", username="player4"), ("player4",)),
    ),
)
def test_aliases(player: Player, aliases: tuple[str, ...]) -> None:
    assert player.aliases == aliases


def test_create_known_player(technoblade_playerdata: Mapping[str, object]) -> None:
    fkdr = 20124 / 260
    stars = bedwars_level_from_exp(1076936)
    target = KnownPlayer(
        username="Technoblade",
        uuid="b876ec32e396476ba1158438d83c67d4",
        stars=stars,
        stats=Stats(
            index=stars * fkdr**2,
            fkdr=20124 / 260,
            kdr=7707 / 7578,
            bblr=6591 / 592,
            wlr=4924 / 259,
            winstreak=None,
            winstreak_accurate=False,
            kills=7707,
            finals=20124,
            beds=6591,
            wins=4924,
        ),
    )

    result = create_known_player(
        playerdata=technoblade_playerdata,
        username="Technoblade",
        uuid="b876ec32e396476ba1158438d83c67d4",
        nick=None,
    )

    assert result == target


def test_create_known_player_seeecret(
    seeecret_playerdata: Mapping[str, object]
) -> None:
    fkdr = 12378
    stars = 76 + 805 / 5000
    target = KnownPlayer(
        username="Seeecret",
        uuid="437e8dfc93e6490ca90bde65f1b29d62",
        stars=stars,
        stats=Stats(
            index=stars * fkdr**2,
            fkdr=fkdr,
            kdr=3860 / 3304,
            bblr=3272,
            wlr=3238,
            winstreak=3238,
            winstreak_accurate=True,
            kills=3860,
            finals=fkdr,
            beds=3272,
            wins=3238,
        ),
    )

    result = create_known_player(
        playerdata=seeecret_playerdata,
        username="Seeecret",
        uuid="437e8dfc93e6490ca90bde65f1b29d62",
        nick=None,
    )

    assert result == target


def test_create_known_player_new() -> None:
    """Assert that a player with 0 wins has 0 winstreak"""
    target = KnownPlayer(
        username="NewPlayer",
        uuid="my-uuid",
        stars=1.0,
        stats=Stats(
            index=0.0,
            fkdr=0,
            kdr=2.0,
            bblr=0,
            wlr=0,
            winstreak=0,
            winstreak_accurate=True,
            kills=10,
            finals=0,
            beds=0,
            wins=0,
        ),
    )

    result = create_known_player(
        playerdata={"stats": {"Bedwars": {"kills_bedwars": 10, "deaths_bedwars": 5}}},
        username="NewPlayer",
        uuid="my-uuid",
        nick=None,
    )

    assert result == target


def test_create_known_player_known_winstreak() -> None:
    target = KnownPlayer(
        username="KnownWinstreak",
        uuid="my-uuid",
        stars=1.0,
        lastLoginMs=1234,
        lastLogoutMs=5678,
        stats=Stats(
            index=0.0,
            fkdr=0.0,
            kdr=0.0,
            bblr=0.0,
            wlr=0.0,
            winstreak=13,
            winstreak_accurate=True,
            kills=0,
            finals=0,
            beds=0,
            wins=0,
        ),
    )

    result = create_known_player(
        playerdata={
            "displayname": "KnownWinstreak",
            "lastLogin": 1234,
            "lastLogout": 5678,
            "stats": {
                "Bedwars": {
                    "winstreak": 13,
                }
            },
        },
        username="KnownWinstreak",
        uuid="my-uuid",
        nick=None,
    )

    assert result == target


def test_create_known_player_broken_data() -> None:
    target = KnownPlayer(
        username="BrokenPlayer",
        uuid="my-uuid",
        stars=1.0,
        lastLoginMs=None,
        lastLogoutMs=None,
        stats=Stats(
            index=0.0,
            fkdr=0.0,
            kdr=0.0,
            bblr=0.0,
            wlr=0.0,
            # 0 wins -> 0 winstreak
            winstreak=0,
            winstreak_accurate=True,
            kills=0,
            finals=0,
            beds=0,
            wins=0,
        ),
    )

    result = create_known_player(
        playerdata={
            "displayname": "BrokenPlayer",
            "lastLogin": "abcd",
            "lastLogout": [],
            "stats": {
                "Bedwars": {
                    "winstreak": (),
                    "Experience": [],
                    "kills_bedwars": "A",
                    "deaths_bedwars": "A",
                    "final_kills_bedwars": {},
                    "final_deaths_bedwars": None,
                    "beds_broken_bedwars": 1e3,
                    "beds_lost_bedwars": 1e-7,
                    "wins_bedwars": b"A",
                    "games_played_bedwars": lambda: 1,
                }
            },
        },
        username="BrokenPlayer",
        uuid="my-uuid",
        nick=None,
    )

    assert result == target
