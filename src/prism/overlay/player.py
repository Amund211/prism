import functools
import operator
from collections.abc import Mapping, Set
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal, Self, TypedDict, TypeVar, assert_never

from prism.calc import bedwars_level_from_exp
from prism.errors import MissingBedwarsStatsError
from prism.hypixel import get_gamemode_stats
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

    dataReceivedAtMs: int
    stats: Stats
    stars: float
    username: str
    uuid: str
    lastLoginMs: int | None = field(default=None)
    lastLogoutMs: int | None = field(default=None)
    nick: str | None = field(default=None)

    @property
    def stats_unknown(self) -> bool:
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

    @property
    def sessiontime_seconds(self) -> float | None:
        if (
            self.lastLoginMs is None
            or self.lastLogoutMs is None
            or self.lastLogoutMs > self.lastLoginMs
            or self.lastLoginMs > self.dataReceivedAtMs
        ):
            # Some stats missing or player seems to be offline
            return None

        return (self.dataReceivedAtMs - self.lastLoginMs) / 1000

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
    """Dataclass holding the stats of a single nicked player"""

    nick: str

    @property
    def stats_unknown(self) -> bool:
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
    def stats_unknown(self) -> bool:
        return False

    @property
    def aliases(self) -> tuple[str, ...]:
        """List of known aliases for the player"""
        return (self.username,)


@dataclass(frozen=True, slots=True)
class UnknownPlayer:
    """A player whose stats are missing due to an unknown error"""

    username: str

    @property
    def stats_unknown(self) -> bool:
        return True

    @property
    def aliases(self) -> tuple[str, ...]:
        """List of known aliases for the player"""
        return (self.username,)


Player = KnownPlayer | NickedPlayer | PendingPlayer | UnknownPlayer


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


PlayerDataField = TypeVar("PlayerDataField")
DefaultType = TypeVar("DefaultType")


def get_playerdata_field(
    playerdata: Mapping[str, object],
    field: str,
    data_type: type[PlayerDataField],
    default: DefaultType,
) -> PlayerDataField | DefaultType:
    """Get a field from the playerdata, fallback if missing or wrong type"""
    value = playerdata.get(field, None)
    if isinstance(value, data_type):
        return value
    return default


def create_known_player(
    dataReceivedAtMs: int,
    playerdata: Mapping[str, object],
    username: str,
    uuid: str,
    nick: str | None = None,
) -> KnownPlayer:
    lastLoginMs = get_playerdata_field(playerdata, "lastLogin", int, None)
    lastLogoutMs = get_playerdata_field(playerdata, "lastLogout", int, None)

    try:
        bw_stats = get_gamemode_stats(playerdata, gamemode="Bedwars")
    except MissingBedwarsStatsError:
        return KnownPlayer(
            dataReceivedAtMs=dataReceivedAtMs,
            username=username,
            nick=nick,
            uuid=uuid,
            lastLoginMs=lastLoginMs,
            lastLogoutMs=lastLogoutMs,
            stars=0,
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

    winstreak = get_playerdata_field(bw_stats, "winstreak", int, None)
    stars = bedwars_level_from_exp(
        get_playerdata_field(bw_stats, "Experience", int, 500)
    )
    kills = get_playerdata_field(bw_stats, "kills_bedwars", int, 0)
    finals = get_playerdata_field(bw_stats, "final_kills_bedwars", int, 0)
    beds = get_playerdata_field(bw_stats, "beds_broken_bedwars", int, 0)
    wins = get_playerdata_field(bw_stats, "wins_bedwars", int, 0)

    if winstreak is None and wins == 0:
        # The winstreak field is not populated until your first win
        # If you have no wins we know you don't have a winstreak
        winstreak = 0

    fkdr = div(finals, get_playerdata_field(bw_stats, "final_deaths_bedwars", int, 0))
    return KnownPlayer(
        dataReceivedAtMs=dataReceivedAtMs,
        username=username,
        nick=nick,
        uuid=uuid,
        stars=stars,
        lastLoginMs=lastLoginMs,
        lastLogoutMs=lastLogoutMs,
        stats=Stats(
            index=stars * fkdr**2,
            fkdr=fkdr,
            kdr=div(kills, get_playerdata_field(bw_stats, "deaths_bedwars", int, 0)),
            bblr=div(beds, get_playerdata_field(bw_stats, "beds_lost_bedwars", int, 0)),
            wlr=div(wins, get_playerdata_field(bw_stats, "losses_bedwars", int, 0)),
            winstreak=winstreak,
            winstreak_accurate=winstreak is not None,
            kills=kills,
            finals=finals,
            beds=beds,
            wins=wins,
        ),
    )
