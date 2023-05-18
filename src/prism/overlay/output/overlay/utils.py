import logging
import webbrowser

from prism.overlay.output.cell_renderer import RenderedStats, render_stats
from prism.overlay.output.config import RatingConfigCollection
from prism.overlay.player import KnownPlayer, NickedPlayer, Player

logger = logging.getLogger(__name__)


OverlayRowData = tuple[str | None, RenderedStats]


def player_to_row(
    player: Player, rating_configs: RatingConfigCollection
) -> OverlayRowData:
    """Create an OverlayRowData from a Player instance"""
    if isinstance(player, NickedPlayer) or (
        isinstance(player, KnownPlayer) and player.nick is not None
    ):
        nickname = player.nick
    else:
        nickname = None

    return nickname, render_stats(player, rating_configs)


def open_url(url: str) -> None:  # pragma: no coverage
    """Open the given url in the user's browser"""
    try:
        webbrowser.open(url)
    except webbrowser.Error:
        logger.exception(f"Error opening {url=}!")
