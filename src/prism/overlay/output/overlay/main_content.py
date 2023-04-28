import logging
import tkinter as tk
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from prism.overlay.output.cell_renderer import pick_columns
from prism.overlay.output.cells import COLUMN_NAMES, ColumnName, InfoCellValue
from prism.overlay.output.overlay.utils import OverlayRowData

if TYPE_CHECKING:  # pragma: nocover
    from prism.overlay.output.overlay.stats_overlay import StatsOverlay

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Cell:
    """A cell in the window described by one text widget"""

    text_widget: tk.Text


OverlayRow = tuple[tk.Button, tuple[Cell, ...]]


class MainContent:  # pragma: nocover
    """Main content for the overlay"""

    def __init__(
        self,
        parent: tk.Misc,
        overlay: "StatsOverlay",
        column_order: tuple[ColumnName, ...],
    ) -> None:
        # Column config
        """Set up a frame containing the main content for the overlay"""
        self.overlay = overlay
        self.column_order = column_order

        self.frame = tk.Frame(parent, background="black")

        # Start with zero rows
        self.rows: list[OverlayRow] = []

        # Frame at the top to display info to the user
        self.info_frame = tk.Frame(self.frame, background="black")
        self.info_frame.pack(side=tk.TOP, expand=True, fill=tk.X)

        self.info_labels: dict[InfoCellValue, tk.Label] = {}

        def shrink_info_when_empty(event: "tk.Event[tk.Frame]") -> None:
            """Manually shrink the info frame when it becomes empty"""
            if not self.info_frame.children:
                self.info_frame.configure(height=1)

        self.info_frame.bind("<Expose>", shrink_info_when_empty)

        # A frame for the stats table
        self.table_frame = tk.Frame(self.frame, background="black")
        self.table_frame.pack(side=tk.TOP)

        # Set up header labels
        for column_index, column_name in enumerate(self.column_order):
            left_justified = column_name == "username"
            header_label = tk.Label(
                self.table_frame,
                text=(str.ljust if left_justified else str.rjust)(
                    COLUMN_NAMES[column_name], 7
                ),
                font=("Consolas", "14"),
                fg="snow",
                bg="black",
            )
            header_label.grid(
                row=1,
                column=column_index + 1,
                sticky="w" if left_justified else "e",
            )

    def create_cell(self, row: int, column: int, sticky: Literal["w", "e"]) -> Cell:
        """Create a cell in the table"""
        text_widget = tk.Text(
            self.table_frame,
            font=("Consolas", 14),
            fg="gray60",  # Color set on each update
            bg="black",
            width=1,  # Width set on each update
            undo=False,
            cursor="arrow",
            height=1,
            wrap="none",
            background="black",
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
        )
        text_widget.grid(row=row, column=column, sticky=sticky)

        return Cell(text_widget)

    def append_row(self) -> None:
        """Add a row of cells to the table"""
        row_index = len(self.rows) + 2

        cells = tuple(
            self.create_cell(
                row=row_index,
                column=column_index + 1,
                sticky="w" if column_name == "username" else "e",
            )
            for column_index, column_name in enumerate(self.column_order)
        )

        edit_button = tk.Button(
            self.table_frame,
            text="✎",
            font=("Consolas", "14"),
            foreground="white",
            disabledforeground="black",
            background="black",
            highlightthickness=0,
            state="disabled",
            command=lambda: None,
            relief="flat",
        )
        edit_button.grid(row=row_index, column=0)

        self.rows.append((edit_button, cells))

    def pop_row(self) -> None:
        """Remove a row of cells from the table"""
        edit_button, cells = self.rows.pop()
        for cell in cells:
            cell.text_widget.destroy()

        edit_button.destroy()

    def set_length(self, length: int) -> None:
        """Add or remove table rows to give the desired length"""
        current_length = len(self.rows)
        if length > current_length:
            for i in range(length - current_length):
                self.append_row()
        elif length < current_length:
            for i in range(current_length - length):
                self.pop_row()

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
                font=("Consolas", "14"),
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
            try:
                webbrowser.open(url)
            except webbrowser.Error:
                logger.exception(f"Error opening {url=}!")

        return handler

    def update_content(
        self,
        info_cells: list[InfoCellValue],
        new_rows: list[OverlayRowData] | None,
    ) -> None:
        """Display the new data"""
        # Update the info at the top of the overlay
        self.update_info(info_cells)

        # Set the contents of the table if new data was provided
        if new_rows is not None:
            self.set_length(len(new_rows))

            for i, (nickname, rated_stats) in enumerate(new_rows):
                edit_button, cells = self.rows[i]

                for cell, cell_value in zip(
                    cells, pick_columns(rated_stats, self.column_order)
                ):
                    new_text = cell_value.text

                    cell.text_widget.configure(state=tk.NORMAL)
                    cell.text_widget.delete("1.0", tk.END)
                    cell.text_widget.insert(tk.END, new_text)

                    # Delete old tags
                    for tag in cell.text_widget.tag_names():
                        cell.text_widget.tag_delete(tag)

                    tag_start = 0
                    for i, color_section in enumerate(cell_value.color_sections):
                        tag_name = f"tag{i}"
                        tag_end = tag_start + color_section.length

                        cell.text_widget.tag_add(
                            tag_name, f"1.{tag_start}", f"1.{tag_end}"
                        )
                        cell.text_widget.tag_config(
                            tag_name, foreground=color_section.color
                        )

                        tag_start = tag_end

                    cell.text_widget.configure(
                        fg=cell_value.color_sections[-1].color,
                        state=tk.DISABLED,
                        width=len(new_text),
                    )

                if nickname is None:
                    edit_button.configure(state="disabled", command=lambda: None)
                else:
                    edit_button.configure(
                        state="normal", command=self.make_set_nick_callback(nickname)
                    )

    def make_set_nick_callback(self, nickname: str) -> Callable[[], None]:
        """Create a callback to pass as a command to open the set nick page"""

        def command(self: "MainContent" = self) -> None:
            self.overlay.set_nickname_page.set_content(nickname)
            self.overlay.switch_page("set_nickname")

        return command
