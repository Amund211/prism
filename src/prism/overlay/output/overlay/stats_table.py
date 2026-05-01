import logging
import platform
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from prism.overlay.output.cells import COLUMN_NAMES, CellValue, ColumnName
from prism.overlay.output.overlay.stats_table_controller import (
    GUIRow,
    StatsTableController,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Cell:
    """A cell in the table described by one text widget"""

    text_widget: tk.Text


OverlayRow = tuple[tk.Button, tuple[Cell, ...]]


class StatsTable:  # pragma: nocover
    """Standalone stats-table widget driven by a StatsTableController.

    Owns the `table_frame` plus headers and rows. Takes `on_edit_click` as
    constructor injection so the widget itself has no knowledge of the
    overlay singleton or the set-nickname page.
    """

    def __init__(
        self,
        parent: tk.Misc,
        on_edit_click: Callable[[str], None],
        column_order: tuple[ColumnName, ...],
    ) -> None:
        self.on_edit_click = on_edit_click
        self.column_order = column_order

        self.table_frame = tk.Frame(parent, background="black")
        self.table_frame.pack(side=tk.TOP)
        self.table_frame.grid_columnconfigure(0, pad=4)

        self.rows: list[OverlayRow] = []
        self.header_labels: tuple[tk.Label, ...] = ()
        self._draw_header_labels()

        self.controller = StatsTableController.create(
            set_column_order=self._set_column_order,
            set_row_count=self._set_row_count,
            set_row=self._set_row,
        )

    def tick(
        self,
        new_rows: tuple[GUIRow, ...] | None,
        column_order: tuple[ColumnName, ...],
    ) -> None:
        """Apply one frame of stats updates to the table."""
        self.controller.tick(new_rows, column_order)

    # ----- driver methods (called by the controller) -----

    def _set_column_order(self, new_columns: tuple[ColumnName, ...]) -> None:
        # Cells depend on column count, so we tear rows down here. The
        # controller will re-issue set_row_count + set_row immediately after.
        self._set_row_count(0)
        self.column_order = new_columns
        self._draw_header_labels()

    def _set_row_count(self, n: int) -> None:
        current = len(self.rows)
        if n > current:
            for _ in range(n - current):
                self._append_row()
        elif n < current:
            for _ in range(current - n):
                self._pop_row()

    def _set_row(self, i: int, gui_row: GUIRow) -> None:
        edit_button, cells = self.rows[i]

        for cell, cell_value in zip(cells, gui_row.cells, strict=True):
            self._render_cell(cell, cell_value)

        if gui_row.nickname is None:
            edit_button.configure(state="disabled", command=lambda: None)
        else:
            edit_button.configure(
                state="normal",
                command=self._make_edit_callback(gui_row.nickname),
            )

    # ----- internals -----

    def _draw_header_labels(self) -> None:
        for label in self.header_labels:
            label.destroy()

        labels: list[tk.Label] = []
        for column_index, column_name in enumerate(self.column_order):
            left_justified = column_name == "username"
            header_label = tk.Label(
                self.table_frame,
                text=(str.ljust if left_justified else str.rjust)(
                    COLUMN_NAMES[column_name], 7
                ),
                font=("Consolas", 14),
                fg="snow",
                bg="black",
            )
            header_label.grid(
                row=1,
                column=column_index + 1,
                sticky="w" if left_justified else "e",
            )
            labels.append(header_label)

        self.header_labels = tuple(labels)

    def _create_cell(self, row: int, column: int, sticky: Literal["w", "e"]) -> Cell:
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

    def _append_row(self) -> None:
        row_index = len(self.rows) + 2
        self.table_frame.grid_rowconfigure(row_index, pad=4)

        cells = tuple(
            self._create_cell(
                row=row_index,
                column=column_index + 1,
                sticky="w" if column_name == "username" else "e",
            )
            for column_index, column_name in enumerate(self.column_order)
        )

        edit_button = tk.Button(
            self.table_frame,
            text="✎",
            font=("Consolas", 14 if platform.system() == "Linux" else 12),
            foreground="white",
            disabledforeground="black",
            background="black",
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
            padx=2,
            pady=0,
            state="disabled",
            command=lambda: None,
            relief="flat",
        )
        edit_button.grid(row=row_index, column=0)

        self.rows.append((edit_button, cells))

    def _pop_row(self) -> None:
        edit_button, cells = self.rows.pop()
        for cell in cells:
            cell.text_widget.destroy()
        edit_button.destroy()

    def _render_cell(self, cell: Cell, cell_value: CellValue) -> None:
        text = cell_value.text

        cell.text_widget.configure(state=tk.NORMAL)
        cell.text_widget.delete("1.0", tk.END)
        cell.text_widget.insert(tk.END, text)

        for tag in cell.text_widget.tag_names():
            cell.text_widget.tag_delete(tag)

        tag_start = 0
        for i, color_section in enumerate(cell_value.color_sections):
            tag_name = f"tag{i}"
            tag_end = tag_start + color_section.length
            cell.text_widget.tag_add(tag_name, f"1.{tag_start}", f"1.{tag_end}")
            cell.text_widget.tag_config(tag_name, foreground=color_section.color)
            tag_start = tag_end

        cell.text_widget.configure(
            fg=cell_value.color_sections[-1].color,
            state=tk.DISABLED,
            width=len(text),
        )

    def _make_edit_callback(self, nickname: str) -> Callable[[], None]:
        def callback() -> None:
            self.on_edit_click(nickname)

        return callback
