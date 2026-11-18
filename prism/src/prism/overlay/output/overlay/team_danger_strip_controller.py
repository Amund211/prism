from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

from prism.overlay.output.cells import GUI_COLORS, CellValue, ColorSection
from prism.overlay.team_types import (
    TEAM_DISPLAY_NAMES,
    TEAM_MINECRAFT_COLORS,
    LobbyDangerSummary,
    TeamDangerBannerData,
    danger_tier_to_gui_color,
)


@dataclass
class TeamDangerStripController:
    """State machine for the team danger banner strip.

    Diffs the incoming TeamDangerBannerData against the previous render and
    only invokes set_banner when the banner payload has changed.
    """

    last_banner: TeamDangerBannerData | None
    set_banner: Callable[[TeamDangerBannerData | None], None]

    @classmethod
    def create(
        cls,
        set_banner: Callable[[TeamDangerBannerData | None], None],
    ) -> Self:
        return cls(
            last_banner=None,
            set_banner=set_banner,
        )

    def tick(self, banner: TeamDangerBannerData | None) -> None:
        """Apply one frame of team danger banner updates."""
        if banner != self.last_banner:
            self.last_banner = banner
            self.set_banner(banner)


def format_lobby_danger_banner(
    summary: LobbyDangerSummary | None,
) -> TeamDangerBannerData | None:
    """Format a LobbyDangerSummary into renderable TeamDangerBannerData.

    Returns None if summary is None or there are neither enemy teams nor
    unassigned enemies.
    """
    if summary is None or (not summary.enemy_teams and not summary.unassigned_enemies):
        return None

    # 1. Headline
    headline: CellValue
    if summary.pending_enemy_count > 0:
        headline = CellValue.monochrome(
            f"TEAM DANGER: Loading enemy stats "
            f"({summary.pending_enemy_count} pending)...",
            GUI_COLORS[0],
        )
    elif summary.priority_target is not None:
        target = summary.priority_target
        prefix = (
            "OPENING TARGET (STATS): "
            if summary.phase == "opening"
            else "TOP ALIVE THREAT: "
        )
        badge = f"[{TEAM_DISPLAY_NAMES[target.team]}]"
        carry_part = f", Carry: {target.top_player}" if target.top_player else ""
        details = (
            f" Danger {target.danger_score:.0f} "
            f"({target.alive_count} alive{carry_part})"
        )
        headline = CellValue(
            text=f"{prefix}{badge}{details}",
            color_sections=(
                ColorSection(GUI_COLORS[1], len(prefix)),
                ColorSection(TEAM_MINECRAFT_COLORS[target.team], len(badge)),
                ColorSection(danger_tier_to_gui_color(target.tier), len(details)),
            ),
        )
    else:
        eligible_unassigned = [
            p for p in summary.unassigned_enemies if p.status in ("known", "nicked")
        ]
        if eligible_unassigned:
            top = eligible_unassigned[0]
            prefix = "TOP UNASSIGNED THREAT: "
            player_text = f"{top.username} (Danger {top.danger_score:.0f})"
            suffix = " | /w !r=Name sets team"
            headline = CellValue(
                text=f"{prefix}{player_text}{suffix}",
                color_sections=(
                    ColorSection(GUI_COLORS[1], len(prefix)),
                    ColorSection(danger_tier_to_gui_color(top.tier), len(player_text)),
                    ColorSection(GUI_COLORS[0], len(suffix)),
                ),
            )
        else:
            headline = CellValue.monochrome(
                "TEAM DANGER: Enemy stats unavailable (error)",
                GUI_COLORS[0],
            )

    # 2. Team summary line
    team_summary_line: CellValue | None = None
    if summary.enemy_teams:
        text_parts: list[str] = []
        color_sections: list[ColorSection] = []

        for i, t in enumerate(summary.enemy_teams):
            if i > 0:
                sep = "   "
                text_parts.append(sep)
                color_sections.append(ColorSection(GUI_COLORS[0], len(sep)))

            badge = f"[{TEAM_DISPLAY_NAMES[t.team]}]"
            text_parts.append(badge)
            color_sections.append(
                ColorSection(TEAM_MINECRAFT_COLORS[t.team], len(badge))
            )

            indicator = "*" if t.pending_count else "?" if t.unknown_count else ""
            score_part = f" {t.danger_score:.0f}{indicator} ({t.alive_count})"
            text_parts.append(score_part)
            color_sections.append(
                ColorSection(danger_tier_to_gui_color(t.tier), len(score_part))
            )

        if summary.unassigned_enemies:
            unassigned_text = f"   [UNASSIGNED] {len(summary.unassigned_enemies)}"
            text_parts.append(unassigned_text)
            color_sections.append(ColorSection(GUI_COLORS[0], len(unassigned_text)))

        team_summary_line = CellValue(
            text="".join(text_parts),
            color_sections=tuple(color_sections),
        )

    return TeamDangerBannerData(
        headline=headline,
        team_summary_line=team_summary_line,
    )
