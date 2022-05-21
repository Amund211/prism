"""
Overlay window using tkinter

Inspired by:
https://github.com/notatallshaw/fall_guys_ping_estimate/blob/main/fgpe/overlay.py
"""
import logging
import sys
import tkinter as tk
from dataclasses import dataclass
from traceback import format_exception
from types import TracebackType
from typing import Callable, Generic, Optional, Sequence, TypeVar

logger = logging.getLogger(__name__)

ColumnKey = TypeVar("ColumnKey")


@dataclass
class Cell:
    """A cell in the window described by one label and one stringvar"""

    label: tk.Label
    variable: tk.StringVar


@dataclass
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
        __tb: Optional[TracebackType],
    ) -> None:
        """Exit on callback exception"""
        if not issubclass(__exc, KeyboardInterrupt):
            logger.error(
                "Unhandled exception in event handler: "
                f"'''{''.join(format_exception(__exc, __val, __tb))}'''"
            )
        sys.exit(0)

    def reset_position(self, event: "Optional[tk.Event[tk.Misc]]" = None) -> None:
        """Reset the position of the overlay to the top left corner"""
        self.geometry("+5+5")

    def start_move(self, event: "tk.Event[tk.Misc]") -> None:
        """Store the window and cursor location at the start"""
        self.cursor_x_start = event.x_root
        self.cursor_y_start = event.y_root

        self.window_x_start = self.winfo_x()
        self.window_y_start = self.winfo_y()

    def do_move(self, event: "tk.Event[tk.Misc]") -> None:
        """Move the window to the new location"""
        # Move to where we started + how much the mouse was moved
        x = self.window_x_start + (event.x_root - self.cursor_x_start)
        y = self.window_y_start + (event.y_root - self.cursor_y_start)
        self.geometry(f"+{x}+{y}")


class OverlayWindow(Generic[ColumnKey]):
    """
    Creates an overlay window using tkinter
    Uses the "-topmost" property to always stay on top of other windows
    """

    def __init__(
        self,
        column_order: Sequence[ColumnKey],
        column_names: dict[ColumnKey, str],
        left_justified_columns: set[int],
        close_callback: Callable[[], None],
        minimize_callback: Callable[[], None],
        get_new_data: Callable[
            [], tuple[bool, Optional[CellValue], Optional[list[OverlayRow[ColumnKey]]]]
        ],
        poll_interval: int,
        start_hidden: bool,
        fullscreen_callback: Optional[Callable[[], None]] = None,
    ):
        """Store params and set up controls and header"""
        # Create a root window
        self.root = Root()
        if start_hidden:
            self.hide_window()
        else:
            self.show_window()

        # Column config
        self.column_order = column_order
        self.column_names = column_names
        self.left_justified_columns = left_justified_columns

        self.get_new_data = get_new_data
        self.poll_interval = poll_interval

        toolbar_frame = tk.Frame(self.root, background="black")
        toolbar_frame.pack(side=tk.TOP, expand=True, fill=tk.X)

        grip_label = tk.Label(
            toolbar_frame,
            text="::",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            highlightthickness=1,
        )
        grip_label.pack(side=tk.LEFT, padx=(3, 5))

        grip_label.bind("<ButtonPress-1>", self.root.start_move)
        grip_label.bind("<B1-Motion>", self.root.do_move)
        grip_label.bind("<Double-Button-1>", self.root.reset_position)

        if fullscreen_callback is not None:
            # Fullscreen button
            fullscreen_button = tk.Button(
                toolbar_frame,
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
            toolbar_frame,
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
            self.hide_window()

        minimize_button = tk.Button(
            toolbar_frame,
            text="-",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            highlightthickness=0,
            command=minimize,
            relief="flat",
        )
        minimize_button.pack(side=tk.RIGHT)

        # Info label
        info_variable = tk.StringVar()
        info_label = tk.Label(
            self.root,
            textvariable=info_variable,
            font=("Consolas", "14"),
            fg="red",  # Color set on each update
            bg="black",
        )
        info_label.pack(side=tk.TOP)
        self.info_cell = Cell(info_label, info_variable)

        # A frame for the stats table
        self.table_frame = tk.Frame(self.root, background="black")
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

        # Start with zero rows
        self.rows: list[dict[ColumnKey, Cell]] = []

        # Window geometry
        self.root.overrideredirect(True)
        self.root.reset_position()
        self.root.lift()
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", 0.8)
        self.root.configure(background="black")

        self.root.update_idletasks()

    def show_window(self) -> None:
        """Show the window"""
        self.root.deiconify()
        self.shown = True

    def hide_window(self) -> None:
        """Hide the window"""
        self.root.withdraw()
        self.shown = False

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

    def update_overlay(self) -> None:
        """Get new data to be displayed and display it"""
        show, info_value, new_rows = self.get_new_data()

        # Show or hide the window if the desired state is different from the stored
        if show != self.shown:
            if show:
                self.show_window()
            else:
                self.hide_window()

        # Only update the window if it's shown
        if self.shown:
            # Set the contents of the title label in the window
            if info_value is None:
                self.info_cell.variable.set("")
            else:
                self.info_cell.variable.set(info_value.text)
                self.info_cell.label.configure(fg=info_value.color)

            # Set the contents of the table if new data was provided
            if new_rows is not None:
                self.set_length(len(new_rows))

                for i, new_row in enumerate(new_rows):
                    row = self.rows[i]
                    for column_name in self.column_order:
                        row[column_name].variable.set(new_row[column_name].text)
                        row[column_name].label.configure(fg=new_row[column_name].color)

        self.root.after(self.poll_interval, self.update_overlay)

    def run(self) -> None:
        """Init for the overlay starting the update chain and entering mainloop"""
        self.root.after(self.poll_interval, self.update_overlay)
        self.root.mainloop()
