from typing import Literal, Optional

import pytest

from examples.overlay.stats import (
    KnownPlayer,
    NickedPlayer,
    PendingPlayer,
    Player,
    Stats,
    sort_players,
)


def make_player(
    username: str,
    variant: Literal["nick", "pending", "player"] = "player",
    fkdr: float = 0.0,
    stars: float = 1.0,
    wlr: float = 0.0,
    winstreak: int | None = None,
    winstreak_accurate: bool = False,
    nick: Optional[str] = None,
    uuid: Optional[str] = None,
) -> Player:
    if variant == "player":
        return KnownPlayer(
            stars=stars,
            stats=Stats(
                fkdr=fkdr,
                wlr=wlr,
                winstreak=winstreak,
                winstreak_accurate=winstreak_accurate,
            ),
            username=username,
            nick=nick,
            uuid=uuid,
        )
    elif variant == "nick":
        assert nick is None, "Provide the nick as the username"
        return NickedPlayer(nick=username)
    elif variant == "pending":
        return PendingPlayer(username=username)


# A dict of players to choose from
players: dict[str, Player] = {
    "chad": make_player("chad", fkdr=100, nick="superb_nick"),
    "joe": make_player("joe", fkdr=10),
    "carl": make_player("carl", fkdr=1),
    "carl_jr": make_player("carl_jr", fkdr=1, wlr=1),
    "carl_jr_jr": make_player("carl_jr_jr", fkdr=1, wlr=1, winstreak=10),
    "joseph": make_player("joseph", fkdr=1, wlr=2),
    "amazing_nick": make_player("amazing_nick", variant="nick"),
    "bad_nick": make_player("bad_nick", variant="nick"),
    "maurice": make_player("maurice", variant="pending"),
    "alfred": make_player("alfred", variant="pending"),
}


@pytest.mark.parametrize(
    "players, party_members, result",
    (
        # Joe has better fkdr than Carl
        ([players["carl"], players["joe"]], {}, [players["joe"], players["carl"]]),
        ([players["joe"], players["carl"]], {}, [players["joe"], players["carl"]]),
        # Carl jr. jr. > Carl jr. > Carl
        (
            [players["carl_jr"], players["carl"], players["carl_jr_jr"]],
            {},
            [players["carl_jr_jr"], players["carl_jr"], players["carl"]],
        ),
        # If the juniors are on our team though, they get sorted last
        (
            [players["carl_jr"], players["carl"], players["carl_jr_jr"]],
            {"carl_jr_jr"},
            [players["carl_jr"], players["carl"], players["carl_jr_jr"]],
        ),
        (
            [players["carl_jr"], players["carl"], players["carl_jr_jr"]],
            {"carl_jr_jr", "carl_jr"},
            [players["carl"], players["carl_jr_jr"], players["carl_jr"]],
        ),
        # Joseph outperforms all the Carls on wlr
        (
            [
                players["carl_jr"],
                players["carl"],
                players["joseph"],
                players["carl_jr_jr"],
            ],
            {},
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
            {},
            [players["bad_nick"], players["amazing_nick"], players["joe"]],
        ),
        # Pending players get sorted at the bottom (above teammates)
        (
            [players["joe"], players["maurice"], players["alfred"]],
            {},
            [players["joe"], players["maurice"], players["alfred"]],
        ),
        (
            [players["joe"], players["maurice"], players["alfred"]],
            {"joe"},
            [players["maurice"], players["alfred"], players["joe"]],
        ),
        (
            [players["joe"], players["maurice"], players["alfred"]],
            {"joe", "maurice"},
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
            {},
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
        ([players["chad"], players["joe"]], {}, [players["chad"], players["joe"]]),
        (
            [players["chad"], players["joe"]],
            {"chad"},
            [players["joe"], players["chad"]],
        ),
        # Empty list is ok
        ([], {}, []),
        ([], {"unknown"}, []),
        ([], {"unknown", "unknown2"}, []),
        # Single person is ok
        ([players["joe"]], {}, [players["joe"]]),
        ([players["joe"]], {"unknown", "unknown2"}, [players["joe"]]),
    ),
)
def test_sort_stats(
    players: list[Player], party_members: set[str], result: list[Player]
) -> None:
    """Assert that sort_players functions properly"""
    assert sort_players(players, party_members) == result
