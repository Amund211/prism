from dataclasses import dataclass
from typing import Literal, TypeGuard, assert_never

from prism.overlay.output.cells import GUI_COLORS, CellValue
from prism.overlay.output.color import MinecraftColor

TeamColor = Literal["red", "blue", "green", "yellow"]
PlayerStatStatus = Literal["known", "nicked", "pending", "unknown"]
DangerTier = Literal["low", "medium", "high", "extreme", "pending", "unknown"]
RecommendationPhase = Literal["opening", "midgame"]

ALL_TEAM_COLORS: tuple[TeamColor, ...] = ("red", "blue", "green", "yellow")

TEAM_ORDER_INDEX: dict[TeamColor, int] = {
    "red": 0,
    "blue": 1,
    "green": 2,
    "yellow": 3,
}

TEAM_DISPLAY_NAMES: dict[TeamColor, str] = {
    "red": "RED",
    "blue": "BLUE",
    "green": "GREEN",
    "yellow": "YELLOW",
}

TEAM_SHORT_LABELS: dict[TeamColor, str] = {
    "red": "R",
    "blue": "B",
    "green": "G",
    "yellow": "Y",
}

TEAM_MINECRAFT_COLORS: dict[TeamColor, str] = {
    "red": MinecraftColor.RED,
    "blue": MinecraftColor.BLUE,
    "green": MinecraftColor.GREEN,
    "yellow": MinecraftColor.YELLOW,
}

TEAM_ALIAS_MAP: dict[str, TeamColor] = {
    "red": "red",
    "r": "red",
    "blue": "blue",
    "b": "blue",
    "green": "green",
    "g": "green",
    "yellow": "yellow",
    "y": "yellow",
}


def str_is_team_color(value: str, /) -> TypeGuard[TeamColor]:
    """Return True if value is a valid 3s/4s TeamColor."""
    return value in TEAM_ORDER_INDEX


def danger_tier_to_gui_color(tier: DangerTier) -> str:
    """Map a DangerTier to its GUI color string."""
    match tier:
        case "pending" | "unknown":
            return GUI_COLORS[0]
        case "low":
            return GUI_COLORS[1]
        case "medium":
            return GUI_COLORS[2]
        case "high":
            return GUI_COLORS[3]
        case "extreme":
            return GUI_COLORS[4]
        case _ as unreachable:  # pragma: no cover
            assert_never(unreachable)


@dataclass(frozen=True, slots=True)
class PlayerDanger:
    username: str
    danger_score: float
    status: PlayerStatStatus
    tier: DangerTier
    team: TeamColor | None


@dataclass(frozen=True, slots=True)
class TeamDangerSummary:
    team: TeamColor
    danger_score: float
    total_player_danger: float
    peak_player_danger: float
    tier: DangerTier
    alive_count: int
    known_or_nicked_count: int
    pending_count: int
    unknown_count: int
    top_player: str | None
    is_own_team: bool

    @property
    def is_eligible_target(self) -> bool:
        """True if this team can be recommended as a priority target."""
        return (
            not self.is_own_team
            and self.alive_count > 0
            and self.pending_count == 0
            and self.known_or_nicked_count > 0
        )


@dataclass(frozen=True, slots=True)
class LobbyDangerSummary:
    phase: RecommendationPhase
    enemy_teams: tuple[TeamDangerSummary, ...]
    own_team: TeamDangerSummary | None
    priority_target: TeamDangerSummary | None
    unassigned_enemies: tuple[PlayerDanger, ...]
    pending_enemy_count: int
    unknown_enemy_count: int


@dataclass(frozen=True, slots=True)
class TeamDangerBannerData:
    """Immutable render payload for the TeamDangerStrip widget."""

    headline: CellValue
    team_summary_line: CellValue | None

    @property
    def headline_prefix(self) -> str:
        """The textual content of the headline for prefix matching."""
        return self.headline.text
