import functools
import operator
from collections.abc import Set
from typing import TYPE_CHECKING, Literal, assert_never

from prism.player import KnownPlayer, Player

if TYPE_CHECKING:  # pragma: no coverage
    from prism.overlay.output.cells import ColumnName

GamemodeName = Literal["overall", "solo", "doubles", "threes", "fours"]


def rate_player(
    player: Player, party_members: Set[str], column: "ColumnName", sort_ascending: bool
) -> tuple[bool, bool, str | int | float]:
    """Used as a key function for sorting"""
    is_enemy = player.username not in party_members

    # The value of the stat to sort by
    # NOTE: When column="username" we set stat=0 so that we instead rely on
    #       the fallback sorting by username to order the list.
    #       If we added the username here we would get reverse alphabetical
    stat: int | float | None

    if isinstance(player, KnownPlayer):
        if column == "username":
            stat = 0
        elif column == "stars":
            stat = player.stars
        elif column == "index":
            stat = player.stats.index
        elif column == "fkdr":
            stat = player.stats.fkdr
        elif column == "kdr":
            stat = player.stats.kdr
        elif column == "bblr":
            stat = player.stats.bblr
        elif column == "wlr":
            stat = player.stats.wlr
        elif column == "kills":
            stat = player.stats.kills
        elif column == "finals":
            stat = player.stats.finals
        elif column == "beds":
            stat = player.stats.beds
        elif column == "wins":
            stat = player.stats.wins
        elif column == "winstreak":
            stat = player.stats.winstreak
        elif column == "sessiontime":
            stat = player.sessiontime_seconds
        else:  # pragma: no coverage
            assert_never(column)

        if stat is None:
            # Missing stats sorted to the top
            stat = float("-inf") if sort_ascending else float("inf")
        # Invert the value to sort ascending with a descending sort
        if sort_ascending:
            stat *= -1
    else:
        # Unknown players are always sorted last
        stat = 0 if column == "username" else float("-inf")

    return (is_enemy, player.stats_unknown, stat)


def sort_players(
    players: list[Player],
    party_members: Set[str],
    column: "ColumnName",
    sort_ascending: bool,
) -> list[Player]:
    """
    Sort the players by the given column according to `sort_ascending`.

    Orders party members last.
    Orders players with missing stats first (nick/error, *not* pending).
    Falls back to alpabetical by username.
    """
    return list(
        sorted(
            sorted(players, key=operator.attrgetter("username")),
            key=functools.partial(
                rate_player,
                party_members=party_members,
                column=column,
                sort_ascending=sort_ascending,
            ),
            reverse=True,
        )
    )
