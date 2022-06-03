import logging
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Callable, Literal, Union, overload

from prism.utils import truncate_float

if TYPE_CHECKING:  # pragma: nocover
    from examples.overlay.antisniper_api import Winstreaks

GamemodeName = Literal["overall", "solo", "doubles", "threes", "fours"]

StatName = Literal["stars", "fkdr", "wlr", "winstreak"]
InfoName = Literal["username"]
PropertyName = Literal[StatName, InfoName]


logger = logging.getLogger(__name__)


@dataclass(order=True, frozen=True)
class Stats:
    """Dataclass holding a collection of stats"""

    fkdr: float
    wlr: float
    winstreak: int | None = field(compare=False)
    winstreak_accurate: bool = field(compare=False)

    def update_winstreak(
        self, winstreak: int | None, winstreak_accurate: bool
    ) -> "Stats":
        """Update the winstreak in this stat collection"""
        return replace(
            self,
            winstreak=winstreak,
            winstreak_accurate=winstreak_accurate,
        )


@dataclass(order=True, frozen=True)
class KnownPlayer:
    """Dataclass holding the stats of a single player"""

    stats: Stats
    stars: float
    username: str
    uuid: str | None = field(compare=False)
    nick: str | None = field(default=None, compare=False)

    @property
    def stats_hidden(self) -> bool:
        """Return True if the player has hidden stats (is assumed to be nicked)"""
        return False

    @overload
    def get_value(self, name: StatName) -> Union[int, float, None]:
        ...  # pragma: nocover

    @overload
    def get_value(self, name: InfoName) -> str:
        ...  # pragma: nocover

    def get_value(self, name: PropertyName) -> Union[str, int, float, None]:
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
        self, winstreaks: "Winstreaks", winstreaks_accurate: bool
    ) -> "KnownPlayer":
        """Update the winstreaks for a player"""
        return replace(
            self,
            stats=self.stats.update_winstreak(
                winstreak=winstreaks["overall"], winstreak_accurate=winstreaks_accurate
            ),
        )


@dataclass(order=True, frozen=True)
class NickedPlayer:
    """Dataclass holding the stats of a single player assumed to be nicked"""

    nick: str

    @property
    def stats_hidden(self) -> bool:
        """Return True if the player has hidden stats (is assumed to be nicked)"""
        return True

    def get_value(self, name: PropertyName) -> Union[int, float]:
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


@dataclass(order=True, frozen=True)
class PendingPlayer:
    """Dataclass holding the stats of a single player whose stats are pending"""

    username: str

    @property
    def stats_hidden(self) -> bool:
        """Return True if the player has hidden stats (is assumed to be nicked)"""
        return False

    def get_value(self, name: PropertyName) -> Union[int, float]:
        """Get the given stat from this player (unknown in this case)"""
        return float("-inf")

    def get_string(self, name: PropertyName) -> str:
        """Get a string representation of the given stat (unknown)"""
        if name == "username":
            return self.username

        return "-"


Player = Union[KnownPlayer, NickedPlayer, PendingPlayer]


RatePlayerReturn = tuple[bool, bool, Player]


def rate_player(
    party_members: set[str],
) -> Callable[[Player], RatePlayerReturn]:
    def rate_stats(player: Player) -> RatePlayerReturn:
        """Used as a key function for sorting"""
        is_enemy = player.username not in party_members
        if not isinstance(player, KnownPlayer):
            # Hack to compare other Player instances by username only
            placeholder_stats = KnownPlayer(
                username=player.username,
                uuid=None,
                stars=0,
                stats=Stats(
                    fkdr=0,
                    wlr=0,
                    winstreak=0,
                    winstreak_accurate=True,
                ),
            )
            return (is_enemy, player.stats_hidden, placeholder_stats)

        return (is_enemy, player.stats_hidden, player)

    return rate_stats


def sort_players(players: list[Player], party_members: set[str]) -> list[Player]:
    """Sort the stats based on fkdr. Order party members last"""
    return list(
        sorted(
            players,
            key=rate_player(party_members),
            reverse=True,
        )
    )
