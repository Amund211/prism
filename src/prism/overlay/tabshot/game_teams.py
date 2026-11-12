"""Teams read from tab screenshots, for the current game"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Self

from prism.overlay.tabshot.screenshot import Team

# Trial branch: colors clear soon, so each Tab press shows a fresh result
TEAM_COLOR_SECONDS = 8.0


@dataclass(frozen=True, slots=True)
class GameTeams:
    """Immutable: replace the whole object to update it from another thread"""

    game_start: float | None = None
    teams: Mapping[str, Team] = field(default_factory=lambda: MappingProxyType({}))
    set_at: float = 0.0

    def replace(
        self, game_start: float | None, new: Mapping[str, Team], *, now: float
    ) -> Self:
        return type(self)(game_start, MappingProxyType(dict(new)), now)

    def for_game(self, game_start: float | None, *, now: float) -> Mapping[str, Team]:
        if game_start != self.game_start or now - self.set_at >= TEAM_COLOR_SECONDS:
            return {}
        return self.teams
