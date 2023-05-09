import functools
import operator
from collections.abc import Set
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal, Self, TypedDict, assert_never

from prism.calc import bedwars_level_from_exp
from prism.hypixel import MissingStatsError, get_gamemode_stats
from prism.utils import div

if TYPE_CHECKING:  # pragma: no coverage
    from prism.overlay.output.cells import ColumnName

GamemodeName = Literal["overall", "solo", "doubles", "threes", "fours"]


class Winstreaks(TypedDict):
    """Dict holding winstreaks for each core gamemode"""

    overall: int | None
    solo: int | None
    doubles: int | None
    threes: int | None
    fours: int | None


MISSING_WINSTREAKS = Winstreaks(
    overall=None, solo=None, doubles=None, threes=None, fours=None
)


@dataclass(frozen=True, slots=True)
class Stats:
    """Dataclass holding a collection of stats"""

    index: float
    fkdr: float
    kdr: float
    bblr: float
    wlr: float
    winstreak: int | None
    winstreak_accurate: bool
    kills: int
    finals: int
    beds: int
    wins: int

    def update_winstreak(self, winstreak: int | None, winstreak_accurate: bool) -> Self:
        """Update the winstreak in this stat collection"""
        if self.winstreak_accurate or self.winstreak is not None:
            return self

        return replace(
            self,
            winstreak=winstreak,
            winstreak_accurate=winstreak_accurate,
        )


@dataclass(frozen=True, slots=True)
class KnownPlayer:
    """Dataclass holding the stats of a single player"""

    stats: Stats
    stars: float
    username: str
    uuid: str
    channel: str
    nick: str | None = field(default=None)

    @property
    def stats_hidden(self) -> bool:
        """Return True if the player has hidden stats (is assumed to be nicked)"""
        return False

    @property
    def is_missing_winstreaks(self) -> bool:
        """Return True if the player is missing winstreak stats in any gamemode"""
        return self.stats.winstreak is None

    @property
    def aliases(self) -> tuple[str, ...]:
        """List of known aliases for the player"""
        aliases = [self.username]
        if self.nick is not None:
            aliases.append(self.nick)
        return tuple(aliases)

    def update_winstreaks(
        self,
        overall: int | None,
        solo: int | None,
        doubles: int | None,
        threes: int | None,
        fours: int | None,
        winstreaks_accurate: bool,
    ) -> Self:
        """Update the winstreaks for a player"""
        return replace(
            self,
            stats=self.stats.update_winstreak(
                winstreak=overall, winstreak_accurate=winstreaks_accurate
            ),
        )


@dataclass(frozen=True, slots=True)
class NickedPlayer:
    """Dataclass holding the stats of a single player assumed to be nicked"""

    nick: str

    @property
    def stats_hidden(self) -> bool:
        """Return True if the player has hidden stats (is assumed to be nicked)"""
        return True

    @property
    def aliases(self) -> tuple[str, ...]:
        """List of known aliases for the player"""
        return (self.nick,)

    @property
    def username(self) -> str:
        """Display the username as the nick"""
        return self.nick


@dataclass(frozen=True, slots=True)
class PendingPlayer:
    """Dataclass holding the stats of a single player whose stats are pending"""

    username: str

    @property
    def stats_hidden(self) -> bool:
        """Return True if the player has hidden stats (is assumed to be nicked)"""
        return False

    @property
    def aliases(self) -> tuple[str, ...]:
        """List of known aliases for the player"""
        return (self.username,)


Player = KnownPlayer | NickedPlayer | PendingPlayer


def rate_player(
    player: Player, party_members: Set[str], column: "ColumnName"
) -> tuple[bool, bool, str | int | float]:
    """Used as a key function for sorting"""
    is_enemy = player.username not in party_members

    # The value of the stat to sort by
    # NOTE: When column="username" we set stat=0 so that we instead rely on
    #       the fallback sorting by username to order the list.
    #       If we added the username here we would get reverse alphabetical
    stat: int | float

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
            stat = (
                player.stats.winstreak
                if player.stats.winstreak is not None
                else float("inf")
            )
        elif column == "channel":
            stat = player.channel
        else:  # pragma: no coverage
            assert_never(column)
    else:
        stat = 0 if column == "username" else float("-inf")

    return (is_enemy, player.stats_hidden, stat)


def sort_players(
    players: list[Player], party_members: Set[str], column: "ColumnName"
) -> list[Player]:
    """
    Sort the players by the given column in reverse order (largest at the top)

    Falls back to alpabetical by username.
    Orders party members last.
    """
    return list(
        sorted(
            sorted(players, key=operator.attrgetter("username")),
            key=functools.partial(
                rate_player, party_members=party_members, column=column
            ),
            reverse=True,
        )
    )


def create_known_player(
    playerdata: dict[str, Any], username: str, uuid: str, nick: str | None = None
) -> KnownPlayer:
    try:
        bw_stats = get_gamemode_stats(playerdata, gamemode="Bedwars")
    except MissingStatsError:
        return KnownPlayer(
            username=username,
            nick=nick,
            uuid=uuid,
            stars=0,
            channel="-",
            stats=Stats(
                index=0,
                fkdr=0,
                kdr=0,
                bblr=0,
                wlr=0,
                winstreak=0,
                winstreak_accurate=True,
                kills=0,
                finals=0,
                beds=0,
                wins=0,
            ),
        )

    winstreak = bw_stats.get("winstreak", None)
    stars = bedwars_level_from_exp(bw_stats.get("Experience", 500))
    kills = bw_stats.get("kills_bedwars", 0)
    finals = bw_stats.get("final_kills_bedwars", 0)
    beds = bw_stats.get("beds_broken_bedwars", 0)
    wins = bw_stats.get("wins_bedwars", 0)

    if winstreak is None and wins == 0:
        # The winstreak field is not populated until your first win
        # If you have no wins we know you don't have a winstreak
        winstreak = 0

    fkdr = div(finals, bw_stats.get("final_deaths_bedwars", 0))
    return KnownPlayer(
        username=username,
        nick=nick,
        uuid=uuid,
        stars=stars,
        channel=playerdata.get("channel", "-"),
        stats=Stats(
            index=stars * fkdr**2,
            fkdr=fkdr,
            kdr=div(kills, bw_stats.get("deaths_bedwars", 0)),
            bblr=div(beds, bw_stats.get("beds_lost_bedwars", 0)),
            wlr=div(wins, bw_stats.get("games_played_bedwars", 0) - wins),
            winstreak=winstreak,
            winstreak_accurate=winstreak is not None,
            kills=kills,
            finals=finals,
            beds=beds,
            wins=wins,
        ),
    )
