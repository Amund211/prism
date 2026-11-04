"""Teams read from tab screenshots, for the current game"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Self

from prism.overlay.tabshot.screenshot import Team


@dataclass(frozen=True, slots=True)
class GameTeams:
    """Immutable: replace the whole object to update it from another thread"""

    game_start: float | None = None
    teams: Mapping[str, Team] = field(default_factory=lambda: MappingProxyType({}))

    def merge(self, game_start: float | None, new: Mapping[str, Team]) -> Self:
        """Add new teams. A new game start resets the old teams."""
        old = self.teams if game_start == self.game_start else {}
        return type(self)(game_start, MappingProxyType({**old, **new}))

    def for_game(self, game_start: float | None) -> Mapping[str, Team]:
        return self.teams if game_start == self.game_start else {}
