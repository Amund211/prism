from dataclasses import dataclass
from typing import Self

from prism.overlay.team_types import TeamColor, TeamDangerBannerData


@dataclass(slots=True)
class RushPopupController:
    timeout_seconds: float = 10.0
    last_handled_who_counter: int = 0
    popup_deadline: float | None = None
    is_active: bool = False
    last_banner: TeamDangerBannerData | None = None
    last_player_teams: frozenset[tuple[str, TeamColor]] = frozenset()

    @classmethod
    def create(cls, timeout_seconds: float = 10.0) -> Self:
        return cls(timeout_seconds=timeout_seconds)

    def tick(
        self,
        now: float,
        who_counter: int,
        in_lobby_or_game: bool,
        banner: TeamDangerBannerData | None,
        player_teams: frozenset[tuple[str, TeamColor]] = frozenset(),
    ) -> TeamDangerBannerData | None:
        """
        Determine whether the rush pop-up card should be shown and return its data.
        """
        if not in_lobby_or_game:
            self.is_active = False
            self.popup_deadline = None
            self.last_handled_who_counter = who_counter
            self.last_banner = None
            self.last_player_teams = player_teams
            return None

        if player_teams != self.last_player_teams:
            if banner is not None and not banner.headline_prefix.startswith(
                "TEAM DANGER: Loading"
            ):
                self.is_active = True
                self.popup_deadline = now + self.timeout_seconds
                self.last_banner = banner
            self.last_player_teams = player_teams

        # Check if a new /who calculation just finished
        if who_counter > self.last_handled_who_counter:
            if banner is not None and not banner.headline_prefix.startswith(
                "TEAM DANGER: Loading"
            ):
                self.last_handled_who_counter = who_counter
                self.is_active = True
                self.popup_deadline = now + self.timeout_seconds
                self.last_banner = banner
                return banner
            # Still loading or no banner yet; wait

        if self.is_active:
            if self.popup_deadline is not None and now >= self.popup_deadline:
                self.is_active = False
                self.popup_deadline = None
                self.last_banner = None
                return None

            # Keep banner fresh if updated during display window
            if banner is not None and not banner.headline_prefix.startswith(
                "TEAM DANGER: Loading"
            ):
                self.last_banner = banner
            return self.last_banner

        return None
