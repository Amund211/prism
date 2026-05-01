import logging
import tkinter as tk
from collections.abc import Callable
from typing import TYPE_CHECKING

from prism.overlay.output.cell_renderer import pick_columns
from prism.overlay.output.cells import ColumnName, InfoCellValue
from prism.overlay.output.overlay.stats_table import StatsTable
from prism.overlay.output.overlay.stats_table_controller import (
    GUIRow,
    maybe_add_tags_column,
)
from prism.overlay.output.overlay.utils import OverlayRowData, open_url

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

        # Frame at the top to display info to the user
        self.info_frame = tk.Frame(self.frame, background="black")
        self.info_frame.pack(side=tk.TOP, expand=True, fill=tk.X)

        self.info_labels: dict[InfoCellValue, tk.Label] = {}

        def shrink_info_when_empty(event: "tk.Event[tk.Frame]") -> None:
            """Manually shrink the info frame when it becomes empty"""
            if not self.info_frame.children:
                self.info_frame.configure(height=1)

        self.info_frame.bind("<Expose>", shrink_info_when_empty)

        # The reusable stats-table widget
        self.stats_table = StatsTable(
            parent=self.frame,
            on_edit_click=self._on_edit_click,
            column_order=column_order,
        )

    def update_info(self, info_cells: list[InfoCellValue]) -> None:
        """Update the list of info cells at the top of the overlay"""
        to_remove = set(self.info_labels.keys()) - set(info_cells)
        to_add = set(info_cells) - set(self.info_labels.keys())

        # Remove old labels
        for cell in to_remove:
            label = self.info_labels.pop(cell)
            label.destroy()

        # Add new labels
        for cell in to_add:
            label = tk.Label(
                self.info_frame,
                text=cell.text,
                font=("Consolas", 14),
                fg=cell.color,  # Color set on each update
                bg="black",
            )

            if cell.url is not None:
                label.config(cursor="hand2")
                label.bind("<Button-1>", self._make_link_click_handler(cell.url))

            label.pack(side=tk.TOP)
            self.info_labels[cell] = label

    def _make_link_click_handler(
        self, url: str
    ) -> Callable[["tk.Event[tk.Label]"], None]:
        def handler(event: "tk.Event[tk.Label]") -> None:
            open_url(url)

        return handler

    def update_content(
        self,
        info_cells: list[InfoCellValue],
        new_rows: list[OverlayRowData] | None,
    ) -> None:
        """Display the new data"""
        self.update_info(info_cells)

        if new_rows is None:
            return

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
