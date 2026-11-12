import logging
import webbrowser
from dataclasses import replace

from prism.overlay.output.cell_renderer import RenderedStats, render_stats
from prism.overlay.output.cells import CellValue, ColorSection
from prism.overlay.output.config import RatingConfigCollection
from prism.overlay.team_types import (
    TEAM_MINECRAFT_COLORS,
    TEAM_SHORT_LABELS,
    TeamColor,
)
from prism.player import KnownPlayer, NickedPlayer, Player, UnknownPlayer

logger = logging.getLogger(__name__)


OverlayRowData = tuple[str | None, RenderedStats]


def player_to_row(
    player: Player,
    rating_configs: RatingConfigCollection,
) -> OverlayRowData:
    """Create an OverlayRowData from a Player instance"""
    if isinstance(player, NickedPlayer) or (
        isinstance(player, KnownPlayer) and player.nick is not None
    ):
        nickname = player.nick
    elif isinstance(player, UnknownPlayer):
        # Allow users to manually denick unknown players
        # If an error occurs while getting a player's stats, the user should not have to
        # wait for the stats to get refetched before being allowed to set a denick
        nickname = player.username
    else:
        nickname = None

    return nickname, render_stats(player, rating_configs)


def with_team_color(row: OverlayRowData, team: TeamColor | None) -> OverlayRowData:
    """Prepend team short label to row's username cell colored with team color."""
    if team is None:
        return row
    nickname, stats = row
    prefix = f"[{TEAM_SHORT_LABELS[team]}] "
    username_cell = CellValue(
        text=f"{prefix}{stats.username.text}",
        color_sections=(
            ColorSection(TEAM_MINECRAFT_COLORS[team], len(prefix)),
            *stats.username.color_sections,
        ),
    )
    return nickname, replace(stats, username=username_cell)


def open_url(url: str) -> None:  # pragma: no coverage
    """Open the given url in the user's browser"""
    try:
        webbrowser.open(url)
    except webbrowser.Error:
        logger.exception(f"Error opening {url=}!")
