import logging
import tkinter as tk
from typing import TYPE_CHECKING

from prism.overlay.output.cell_renderer import pick_columns
from prism.overlay.output.cells import ColumnName, InfoCellValue
from prism.overlay.output.overlay.info_strip import InfoStrip
from prism.overlay.output.overlay.stats_table import StatsTable
from prism.overlay.output.overlay.stats_table_controller import (
    GUIRow,
    maybe_add_tags_column,
)
from prism.overlay.output.overlay.team_danger_strip import TeamDangerStrip
from prism.overlay.output.overlay.utils import OverlayRowData, open_url
from prism.overlay.team_types import TeamDangerBannerData

if TYPE_CHECKING:  # pragma: nocover
    from prism.overlay.output.overlay.stats_overlay import StatsOverlay

logger = logging.getLogger(__name__)


class MainContent:  # pragma: nocover
    """Main content for the overlay: info-cell strip on top of the stats table."""

    def __init__(
        self,
        parent: tk.Misc,
        overlay: "StatsOverlay",
        column_order: tuple[ColumnName, ...],
    ) -> None:
        self.overlay = overlay

        self.frame = tk.Frame(parent, background="black")

        self.info_strip = InfoStrip(parent=self.frame, on_link_click=open_url)
        self.team_danger_strip = TeamDangerStrip(parent=self.frame)

        self.stats_table = StatsTable(
            parent=self.frame,
            on_edit_click=self._on_edit_click,
            column_order=column_order,
        )

    def update_content(
        self,
        info_cells: list[InfoCellValue],
        new_rows: list[OverlayRowData] | None,
        team_danger_banner: TeamDangerBannerData | None = None,
    ) -> None:
        """Display the new data"""
        self.info_strip.tick(tuple(info_cells))

        if new_rows is None:
            return

        self.team_danger_strip.tick(team_danger_banner)

        rows_tuple = tuple(new_rows)
        column_order = maybe_add_tags_column(
            self.overlay.controller.settings.column_order, rows_tuple
        )

        gui_rows = tuple(
            GUIRow(
                cells=pick_columns(rated_stats, column_order),
                nickname=nickname,
            )
            for nickname, rated_stats in rows_tuple
        )

        self.stats_table.tick(gui_rows, column_order)

    def _on_edit_click(self, nickname: str) -> None:
        self.overlay.set_nickname_page.set_content(nickname)
        self.overlay.switch_page("set_nickname")
