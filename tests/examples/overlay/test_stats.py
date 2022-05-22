from typing import Literal, Optional

import pytest

from examples.overlay.stats import (
    NickedPlayer,
    PendingPlayer,
    PlayerStats,
    Stats,
    sort_stats,
)


def make_stats(
    username: str,
    variant: Literal["nick", "pending", "player"] = "player",
    fkdr: float = 0.0,
    stars: float = 1.0,
    wlr: float = 0.0,
    winstreak: int | None = None,
    winstreak_accurate: bool = False,
    nick: Optional[str] = None,
    uuid: Optional[str] = None,
) -> Stats:
    if variant == "player":
        return PlayerStats(
            fkdr=fkdr,
            stars=stars,
            wlr=wlr,
            winstreak=winstreak,
            winstreak_accurate=winstreak_accurate,
            username=username,
            nick=nick,
            uuid=uuid,
        )
    elif variant == "nick":
        return NickedPlayer(username=username)
    elif variant == "pending":
        return PendingPlayer(username=username)


# A dict of stats to choose from
stats: dict[str, Stats] = {
    "chad": make_stats("chad", fkdr=100, nick="superb_nick"),
    "joe": make_stats("joe", fkdr=10),
    "carl": make_stats("carl", fkdr=1),
    "carl_jr": make_stats("carl_jr", fkdr=1, wlr=1),
    "carl_jr_jr": make_stats("carl_jr_jr", fkdr=1, wlr=1, winstreak=10),
    "joseph": make_stats("joseph", fkdr=1, wlr=2),
    "amazing_nick": make_stats("amazing_nick", variant="nick"),
    "bad_nick": make_stats("bad_nick", variant="nick"),
    "maurice": make_stats("maurice", variant="pending"),
    "alfred": make_stats("alfred", variant="pending"),
}


@pytest.mark.parametrize(
    "stats, party_members, result",
    (
        # Joe has better fkdr than Carl
        ([stats["carl"], stats["joe"]], {}, [stats["joe"], stats["carl"]]),
        ([stats["joe"], stats["carl"]], {}, [stats["joe"], stats["carl"]]),
        # Carl jr. jr. > Carl jr. > Carl
        (
            [stats["carl_jr"], stats["carl"], stats["carl_jr_jr"]],
            {},
            [stats["carl_jr_jr"], stats["carl_jr"], stats["carl"]],
        ),
        # If the juniors are on our team though, they get sorted last
        (
            [stats["carl_jr"], stats["carl"], stats["carl_jr_jr"]],
            {"carl_jr_jr"},
            [stats["carl_jr"], stats["carl"], stats["carl_jr_jr"]],
        ),
        (
            [stats["carl_jr"], stats["carl"], stats["carl_jr_jr"]],
            {"carl_jr_jr", "carl_jr"},
            [stats["carl"], stats["carl_jr_jr"], stats["carl_jr"]],
        ),
        # Joseph outperforms all the Carls on wlr
        (
            [stats["carl_jr"], stats["carl"], stats["joseph"], stats["carl_jr_jr"]],
            {},
            [stats["joseph"], stats["carl_jr_jr"], stats["carl_jr"], stats["carl"]],
        ),
        (
            [stats["carl_jr"], stats["carl"], stats["joseph"], stats["carl_jr_jr"]],
            {"joseph", "our_username"},
            [stats["carl_jr_jr"], stats["carl_jr"], stats["carl"], stats["joseph"]],
        ),
        # Nicks get sorted at the top - sorted by username descending
        (
            [stats["joe"], stats["amazing_nick"], stats["bad_nick"]],
            {},
            [stats["bad_nick"], stats["amazing_nick"], stats["joe"]],
        ),
        # Pending players get sorted at the bottom (above teammates)
        (
            [stats["joe"], stats["maurice"], stats["alfred"]],
            {},
            [stats["joe"], stats["maurice"], stats["alfred"]],
        ),
        (
            [stats["joe"], stats["maurice"], stats["alfred"]],
            {"joe"},
            [stats["maurice"], stats["alfred"], stats["joe"]],
        ),
        (
            [stats["joe"], stats["maurice"], stats["alfred"]],
            {"joe", "maurice"},
            [stats["alfred"], stats["joe"], stats["maurice"]],
        ),
        # Both pending players and nicks and real players
        (
            [
                stats["carl"],
                stats["joe"],
                stats["maurice"],
                stats["alfred"],
                stats["amazing_nick"],
                stats["bad_nick"],
            ],
            {},
            [
                stats["bad_nick"],
                stats["amazing_nick"],
                stats["joe"],
                stats["carl"],
                stats["maurice"],
                stats["alfred"],
            ],
        ),
        # Denicked player
        ([stats["chad"], stats["joe"]], {}, [stats["chad"], stats["joe"]]),
        ([stats["chad"], stats["joe"]], {"chad"}, [stats["joe"], stats["chad"]]),
        # Empty list is ok
        ([], {}, []),
        ([], {"unknown"}, []),
        ([], {"unknown", "unknown2"}, []),
        # Single person is ok
        ([stats["joe"]], {}, [stats["joe"]]),
        ([stats["joe"]], {"unknown", "unknown2"}, [stats["joe"]]),
    ),
)
def test_sort_stats(
    stats: list[Stats], party_members: set[str], result: list[Stats]
) -> None:
    """Assert that sort_stats functions properly"""
    assert sort_stats(stats, party_members) == result
