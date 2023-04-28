from prism.overlay.output.cell_renderer import RenderedStats, render_stats
from prism.overlay.output.config import RatingConfigCollection
from prism.overlay.player import KnownPlayer, NickedPlayer, Player

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
