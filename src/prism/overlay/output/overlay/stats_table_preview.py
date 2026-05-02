import logging
import tkinter as tk
from collections.abc import Callable

from prism.overlay.output.cell_renderer import pick_columns
from prism.overlay.output.cells import DEFAULT_COLUMN_ORDER, ColumnName
from prism.overlay.output.config import RatingConfigCollection
from prism.overlay.output.overlay.placeholder_players import PLACEHOLDER_PLAYERS
from prism.overlay.output.overlay.stats_table import StatsTable
from prism.overlay.output.overlay.stats_table_controller import (
    GUIRow,
    maybe_add_tags_column,
)
from prism.overlay.output.overlay.utils import player_to_row
from prism.overlay.rating import sort_players
from prism.player import Player

logger = logging.getLogger(__name__)


class StatsTablePreview:  # pragma: nocover
    """Standalone stats-table preview for the settings page.

    Renders PLACEHOLDER_PLAYERS through the same pipeline as the live overlay
    (sort → render → tag-inject → pick columns → tick) using current settings
    pulled via injected getters. Refresh is invoked by traces / change
    callbacks wired up at each settings input.
    """

    def __init__(
        self,
        parent: tk.Misc,
        get_rating_configs: Callable[[], RatingConfigCollection],
        get_column_order: Callable[[], tuple[ColumnName, ...]],
        get_sort_order: Callable[[], ColumnName],
        get_current_player: Callable[[], Player | None] = lambda: None,
    ) -> None:
        self.get_rating_configs = get_rating_configs
        self.get_column_order = get_column_order
        self.get_sort_order = get_sort_order
        self.get_current_player = get_current_player

        self.frame = tk.Frame(parent, background="black")

        preview_label = tk.Label(
            self.frame,
            text="Preview",
            font=("Consolas", 14),
            foreground="white",
            background="black",
        )
        preview_label.pack(side=tk.TOP, pady=(5, 0))

        # Use the default column order for the initial layout; the first
        # refresh() ticks to whatever the user actually has configured. This
        # lets the preview be constructed before the settings sections exist.
        self.stats_table = StatsTable(
            parent=self.frame,
            on_edit_click=lambda _nickname: None,
            column_order=DEFAULT_COLUMN_ORDER,
        )

    def refresh(self) -> None:
        rating_configs = self.get_rating_configs()
        sort_order = self.get_sort_order()
        sort_ascending = rating_configs.sort_ascending_for(sort_order)

        players: list[Player] = list(PLACEHOLDER_PLAYERS)
        current_player = self.get_current_player()
        if current_player is not None:
            players.append(current_player)

        sorted_players = sort_players(
            players,
            party_members=set(),
            column=sort_order,
            sort_ascending=sort_ascending,
        )

        rows = tuple(player_to_row(p, rating_configs) for p in sorted_players)
        column_order = maybe_add_tags_column(self.get_column_order(), rows)

        gui_rows = tuple(
            GUIRow(
                cells=pick_columns(rated_stats, column_order),
                nickname=nickname,
            )
            for nickname, rated_stats in rows
        )

        self.stats_table.tick(gui_rows, column_order)
