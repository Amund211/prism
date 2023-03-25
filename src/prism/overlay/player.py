from collections.abc import Callable, Set
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Self, TypedDict, overload

from prism.calc import bedwars_level_from_exp
from prism.hypixel import MissingStatsError, get_gamemode_stats
from prism.utils import div, truncate_float

GamemodeName = Literal["overall", "solo", "doubles", "threes", "fours"]

StatName = Literal["stars", "fkdr", "wlr", "winstreak"]
InfoName = Literal["username"]
PropertyName = Literal[StatName, InfoName]

StatsOrder = tuple[float, int, float]
KnownPlayerOrder = tuple[StatsOrder, float, str]


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

    fkdr: float
    wlr: float
    winstreak: int | None
    winstreak_accurate: bool

    def order(self) -> StatsOrder:
        """Return a tuple used to order instances of this class"""
        return (self.fkdr, self.winstreak or 0, self.wlr)

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
    nick: str | None = field(default=None)

    def order(self) -> KnownPlayerOrder:
        """Return a tuple used to order instances of this class"""
        return (self.stats.order(), self.stars, self.username)

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

    @overload
    def get_value(self, name: StatName) -> int | float | None:
        ...  # pragma: nocover

    @overload
    def get_value(self, name: InfoName) -> str:
        ...  # pragma: nocover

    def get_value(self, name: PropertyName) -> str | int | float | None:
        """Get the given stat from this player"""
        if name == "fkdr":
            return self.stats.fkdr
        elif name == "stars":
            return self.stars
        elif name == "wlr":
            return self.stats.wlr
        elif name == "winstreak":
            return self.stats.winstreak
        elif name == "username":
            return self.username + (f" ({self.nick})" if self.nick is not None else "")

    def get_string(self, name: PropertyName) -> str:
        """Get a string representation of the given stat"""
        value = self.get_value(name)
        if value is None:
            return "-"
        elif name == "winstreak":
            return f"{value}{'' if self.stats.winstreak_accurate else '?'}"
        elif isinstance(value, int):
            return str(value)
        elif isinstance(value, str):
            return value
        elif isinstance(value, float):
            return truncate_float(value, 2)
        else:  # pragma: nocover
            raise ValueError(f"{name=} {value=}")

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

    def get_value(self, name: PropertyName) -> int | float:
        """Get the given stat from this player (unknown in this case)"""
        return float("inf")

    def get_string(self, name: PropertyName) -> str:
        """Get a string representation of the given stat (unknown)"""
        if name == "username":
            return self.username

        return "unknown"

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

    def get_value(self, name: PropertyName) -> int | float:
        """Get the given stat from this player (unknown in this case)"""
        return float("-inf")

    def get_string(self, name: PropertyName) -> str:
        """Get a string representation of the given stat (unknown)"""
        if name == "username":
            return self.username

        return "-"


Player = KnownPlayer | NickedPlayer | PendingPlayer


RatePlayerReturn = tuple[bool, bool, KnownPlayerOrder]


def rate_player(
    party_members: Set[str],
) -> Callable[[Player], RatePlayerReturn]:
    def rate_stats(player: Player) -> RatePlayerReturn:
        """Used as a key function for sorting"""
        is_enemy = player.username not in party_members
        if not isinstance(player, KnownPlayer):
            # Hack to compare other Player instances by username only
            order = KnownPlayer(
                username=player.username,
                uuid="placeholder",
                stars=0,
                stats=Stats(
                    fkdr=0,
                    wlr=0,
                    winstreak=0,
                    winstreak_accurate=True,
                ),
            ).order()
            return (is_enemy, player.stats_hidden, order)

        return (is_enemy, player.stats_hidden, player.order())

    return rate_stats


def sort_players(players: list[Player], party_members: Set[str]) -> list[Player]:
    """Sort the stats based on fkdr. Order party members last"""
    return list(
        sorted(
            players,
            key=rate_player(party_members),
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
            stats=Stats(
                fkdr=0,
                wlr=0,
                winstreak=0,
                winstreak_accurate=True,
            ),
        )

    winstreak = bw_stats.get("winstreak", None)
    return KnownPlayer(
        username=username,
        nick=nick,
        uuid=uuid,
        stars=bedwars_level_from_exp(bw_stats.get("Experience", 500)),
        stats=Stats(
            fkdr=div(
                bw_stats.get("final_kills_bedwars", 0),
                bw_stats.get("final_deaths_bedwars", 0),
            ),
            wlr=div(
                bw_stats.get("wins_bedwars", 0),
                bw_stats.get("games_played_bedwars", 0)
                - bw_stats.get("wins_bedwars", 0),
            ),
            winstreak=winstreak,
            winstreak_accurate=winstreak is not None,
        ),
    )
