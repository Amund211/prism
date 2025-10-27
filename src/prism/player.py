from dataclasses import dataclass, field, replace
from typing import Literal, Self, TypedDict

GamemodeName = Literal["overall", "solo", "doubles", "threes", "fours"]

TagSeverity = Literal["none", "medium", "high"]


@dataclass(frozen=True, slots=True)
class Tags:
    """Dataclass holding tags for a player"""

    sniping: TagSeverity
    cheating: TagSeverity


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

    tags: Tags | None = field(default=None)

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

    def set_tags(self, tags: Tags) -> Self:
        """Set the tags for a player"""
        return replace(self, tags=tags)


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
