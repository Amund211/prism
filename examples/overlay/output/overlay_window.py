"""
Overlay window using tkinter

Inspired by:
https://github.com/notatallshaw/fall_guys_ping_estimate/blob/main/fgpe/overlay.py
"""
import logging
import sys
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from traceback import format_exception
from types import TracebackType
from typing import Generic, TypeVar

from examples.overlay import VERSION_STRING

logger = logging.getLogger(__name__)

ColumnKey = TypeVar("ColumnKey")


@dataclass
class Cell:
    """A cell in the window described by one label and one stringvar"""

    label: tk.Label
    variable: tk.StringVar


@dataclass(frozen=True)
class CellValue:
    """A value that can be set to a cell in the window"""

    text: str
    color: str


# One row in the overlay is a dict mapping column name to a cell value
OverlayRow = dict[ColumnKey, CellValue]


class Root(tk.Tk):
    """Root window that exits when an exception occurs in an event handler"""

    def report_callback_exception(
        self,
        __exc: type[BaseException],
        __val: BaseException,
        __tb: TracebackType | None,
    ) -> None:
        """Exit on callback exception"""
        if not issubclass(__exc, KeyboardInterrupt):
            logger.error(
                "Unhandled exception in event handler: "
                f"'''{''.join(format_exception(__exc, __val, __tb))}'''"
            )
        sys.exit(0)


class OverlayWindow:
    """
    Overlay window using the "-topmost" property to always stay on top

    NOTE: May not appear above some fullscreen apps on Windows.
    See `../platform/windows.py` for more info.
    """

    def __init__(self, start_hidden: bool) -> None:
        """Set up window geometry to make the window an overlay"""
        self.hide_task_id: str | None = None
        self.shown: bool  # Set below

        # Create a root window
        self.root = Root()
        if start_hidden:
            self.hide()
        else:
            self.show()

        # Window geometry
        self.root.overrideredirect(True)
        self.root.lift()
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", 0.8)
        self.root.configure(background="black")

        self.reset_position()

    def show(self) -> None:
        """Show the window"""
        self.cancel_scheduled_hide()
        self.root.deiconify()
        self.shown = True

    def hide(self) -> None:
        """Hide the window"""
        self.cancel_scheduled_hide()
        self.root.withdraw()
        self.shown = False

    def schedule_hide(self, timeout: int) -> None:
        """Schedule a hide of the window in `timeout` ms"""
        self.cancel_scheduled_hide()
        self.hide_task_id = self.root.after(timeout, self.hide)

    def cancel_scheduled_hide(self) -> None:
        """Cancel any existing request to hide the window"""
        if self.hide_task_id is not None:
            self.root.after_cancel(self.hide_task_id)
            self.hide_task_id = None

    def reset_position(self, event: "tk.Event[tk.Misc] | None" = None) -> None:
        """Reset the position of the overlay to the top left corner"""
        self.root.geometry("+5+5")

    def start_move(self, event: "tk.Event[tk.Misc]") -> None:
        """Store the window and cursor location at the start"""
        self.cursor_x_start = event.x_root
        self.cursor_y_start = event.y_root

        self.window_x_start = self.root.winfo_x()
        self.window_y_start = self.root.winfo_y()

    def do_move(self, event: "tk.Event[tk.Misc]") -> None:
        """Move the window to the new location"""
        # Move to where we started + how much the mouse was moved
        x = self.window_x_start + (event.x_root - self.cursor_x_start)
        y = self.window_y_start + (event.y_root - self.cursor_y_start)
        self.root.geometry(f"+{x}+{y}")


class Toolbar:
    """Toolbar for the overlay"""

    def __init__(
        self,
        window: OverlayWindow,
        close_callback: Callable[[], None],
        minimize_callback: Callable[[], None],
        fullscreen_callback: Callable[[], None] | None,
    ) -> None:
        """Set up a frame containing the toolbar for the overlay"""
        self.window = window

        self.frame = tk.Frame(self.window.root, background="black")

        grip_label = tk.Label(
            self.frame,
            text="::",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            highlightthickness=1,
        )
        grip_label.pack(side=tk.LEFT, padx=(3, 5))

        grip_label.bind("<ButtonPress-1>", self.window.start_move)
        grip_label.bind("<B1-Motion>", self.window.do_move)
        grip_label.bind("<Double-Button-1>", self.window.reset_position)

        if fullscreen_callback is not None:
            # Fullscreen button
            fullscreen_button = tk.Button(
                self.frame,
                text="Fullscreen",
                font=("Consolas", "14"),
                foreground="white",
                background="black",
                highlightthickness=0,
                command=fullscreen_callback,
                relief="flat",
            )
            fullscreen_button.pack(side=tk.LEFT)

        # Close button
        close_button = tk.Button(
            self.frame,
            text="X",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            highlightthickness=0,
            command=close_callback,
            relief="flat",
        )
        close_button.pack(side=tk.RIGHT)

        # Minimize button
        def minimize() -> None:
            minimize_callback()

            self.window.hide()

        minimize_button = tk.Button(
            self.frame,
            text="-",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            highlightthickness=0,
            command=minimize,
            relief="flat",
        )
        minimize_button.pack(side=tk.RIGHT)

        version_label = tk.Label(
            self.frame,
            text=VERSION_STRING,
            font=("Consolas", "10"),
            foreground="white",
            background="black",
        )
        version_label.pack(side=tk.RIGHT, padx=(0, 5))


class MainContent(Generic[ColumnKey]):
    """Main content for the overlay"""

    def __init__(
        self,
        window: OverlayWindow,
        column_order: Sequence[ColumnKey],
        column_names: dict[ColumnKey, str],
        left_justified_columns: set[int],
    ) -> None:
        # Column config
        """Set up a frame containing the main content for the overlay"""
        self.window = window
        self.column_order = column_order
        self.column_names = column_names
        self.left_justified_columns = left_justified_columns

        self.frame = tk.Frame(self.window.root, background="black")

        # Start with zero rows
        self.rows: list[dict[ColumnKey, Cell]] = []

        # Frame at the top to display info to the user
        self.info_frame = tk.Frame(self.frame, background="black")
        self.info_frame.pack(side=tk.TOP, expand=True, fill=tk.X)

        self.info_labels: dict[CellValue, tk.Label] = {}

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
            header_label = tk.Label(
                self.table_frame,
                text=(
                    str.ljust
                    if column_index in self.left_justified_columns
                    else str.rjust
                )(self.column_names[column_name], 7),
                font=("Consolas", "14"),
                fg="snow",
                bg="black",
            )
            header_label.grid(
                row=1,
                column=column_index,
                sticky="w" if column_index in self.left_justified_columns else "e",
            )

    def append_row(self) -> None:
        """Add a row of labels and stringvars to the table"""
        row_index = len(self.rows) + 2

        new_row: dict[ColumnKey, Cell] = {}
        for column_index, column_name in enumerate(self.column_order):
            string_var = tk.StringVar()
            label = tk.Label(
                self.table_frame,
                font=("Consolas", "14"),
                fg="gray60",  # Color set on each update
                bg="black",
                textvariable=string_var,
            )
            label.grid(
                row=row_index,
                column=column_index,
                sticky="w" if column_index in self.left_justified_columns else "e",
            )
            new_row[column_name] = Cell(label, string_var)

        self.rows.append(new_row)

    def pop_row(self) -> None:
        """Remove a row of labels and stringvars from the table"""
        row = self.rows.pop()
        for column_name in self.column_order:
            row[column_name].label.destroy()

    def set_length(self, length: int) -> None:
        """Add or remove table rows to give the desired length"""
        current_length = len(self.rows)
        if length > current_length:
            for i in range(length - current_length):
                self.append_row()
        elif length < current_length:
            for i in range(current_length - length):
                self.pop_row()

    def update_info(self, info_cells: list[CellValue]) -> None:
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
            label.pack(side=tk.TOP)
            self.info_labels[cell] = label

    def update_content(
        self, info_cells: list[CellValue], new_rows: list[OverlayRow[ColumnKey]] | None
    ) -> None:
        """Display the new data"""
        # Update the info at the top of the overlay
        self.update_info(info_cells)

        # Set the contents of the table if new data was provided
        if new_rows is not None:
            self.set_length(len(new_rows))

            for i, new_row in enumerate(new_rows):
                row = self.rows[i]
                for column_name in self.column_order:
                    row[column_name].variable.set(new_row[column_name].text)
                    row[column_name].label.configure(fg=new_row[column_name].color)


class StatsOverlay(Generic[ColumnKey]):
    """Show bedwars stats in an overlay"""

    def __init__(
        self,
        start_hidden: bool,
        column_order: Sequence[ColumnKey],
        column_names: dict[ColumnKey, str],
        left_justified_columns: set[int],
        close_callback: Callable[[], None],
        minimize_callback: Callable[[], None],
        fullscreen_callback: Callable[[], None] | None,
        get_new_data: Callable[
            [], tuple[bool, list[CellValue], list[OverlayRow[ColumnKey]] | None]
        ],
        poll_interval: int,
        hide_pause: int = 5000,
    ):
        """Set up content in an OverlayWindow"""
        self.poll_interval = poll_interval
        self.get_new_data = get_new_data
        self.hide_pause = hide_pause

        self.last_new_rows: list[OverlayRow[ColumnKey]] | None = None

        self.window = OverlayWindow(start_hidden=start_hidden)

        # Add the toolbar
        self.toolbar = Toolbar(
            self.window,
            close_callback=close_callback,
            minimize_callback=minimize_callback,
            fullscreen_callback=fullscreen_callback,
        )
        self.toolbar.frame.pack(side=tk.TOP, expand=True, fill=tk.X)

        # Add the main content
        self.main_content = MainContent(
            self.window,
            column_order=column_order,
            column_names=column_names,
            left_justified_columns=left_justified_columns,
        )
        self.main_content.frame.pack(side=tk.TOP, fill=tk.BOTH)

        self.window.root.update_idletasks()

    def update_overlay(self) -> None:
        """Get new data to be displayed and display it"""
        show, info_cells, new_rows = self.get_new_data()

        # Show or hide the window if the desired state is different from the stored
        if show != self.window.shown:
            if show:
                self.window.show()
            else:
                self.window.schedule_hide(self.hide_pause)

        # Only update the window if it's shown
        if self.window.shown:
            # Update the table with the new rows
            # Fall back to the last new rows from when the table was hidden
            self.main_content.update_content(info_cells, new_rows or self.last_new_rows)
            self.last_new_rows = None  # Discard any stored rows
        else:
            # Do not update the table when it is hidden, but keep track of the most
            # recent update so we can use that when we show the table again
            if new_rows is not None:
                self.last_new_rows = new_rows

        self.window.root.after(self.poll_interval, self.update_overlay)

    def run(self) -> None:
        """Init for the overlay starting the update chain and entering mainloop"""
        self.window.root.after(self.poll_interval, self.update_overlay)
        self.window.root.mainloop()
