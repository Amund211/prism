"""
Overlay window using tkinter

Inspired by:
https://github.com/notatallshaw/fall_guys_ping_estimate/blob/main/fgpe/overlay.py
"""
import tkinter as tk
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class Cell:
    label: tk.Label
    variable: tk.StringVar


@dataclass
class CellValue:
    text: str
    color: str


OverlayRow = dict[str, CellValue]


class OverlayWindow:
    """
    Creates an overlay window using tkinter
    Uses the "-topmost" property to always stay on top of other Windows
    """

    def __init__(
        self,
        column_names: list[str],
        pretty_column_names: dict[str, str],
        left_justified_columns: set[int],
        close_callback: Callable[[], None],
        minimize_callback: Callable[[], None],
        get_new_data: Callable[
            [], tuple[bool, Optional[CellValue], Optional[list[OverlayRow]]]
        ],
    ):
        # Create a root window
        self.root = tk.Tk()

        # Column config
        self.column_names = column_names
        self.pretty_column_names = pretty_column_names
        self.left_justified_columns = left_justified_columns

        self.get_new_data = get_new_data

        self.shown = False

        amt_columns = len(column_names)
        assert amt_columns >= 3

        # Title label
        title_variable = tk.StringVar()
        title_label = tk.Label(
            self.root,
            textvariable=title_variable,
            font=("Consolas", "14"),
            fg="green3",
            bg="black",
        )
        title_label.grid(row=0, column=0, columnspan=amt_columns - 2)
        self.title_cell = Cell(title_label, title_variable)

        # Minimize label
        def minimize(_: Any) -> None:
            minimize_callback()
            self.hide_window()

        minimize_label = tk.Label(
            self.root, text=" - ", font=("Consolas", "14"), fg="green3", bg="black"
        )
        minimize_label.bind("<Button-1>", minimize)
        minimize_label.grid(row=0, column=amt_columns - 2)

        # Close label
        close_label = tk.Label(
            self.root, text=" X ", font=("Consolas", "14"), fg="green3", bg="black"
        )
        close_label.bind("<Button-1>", lambda _: close_callback())
        close_label.grid(row=0, column=amt_columns - 1)

        self.rows: list[dict[str, Cell]] = []
        for column_index, column_name in enumerate(self.column_names):
            # Set up header labels
            header_label = tk.Label(
                self.root,
                text=(
                    str.ljust
                    if column_index in self.left_justified_columns
                    else str.rjust
                )(self.pretty_column_names[column_name], 7),
                font=("Consolas", "14"),
                fg="green3",
                bg="black",
            )
            header_label.grid(
                row=1,
                column=column_index,
                sticky="w" if column_index in self.left_justified_columns else "e",
            )

        # Window geometry
        self.root.overrideredirect(True)
        self.root.geometry("+5+5")
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
        row_index = len(self.rows) + 2

        new_row: dict[str, Cell] = {}
        for column_index, column_name in enumerate(self.column_names):
            string_var = tk.StringVar()
            label = tk.Label(
                self.root,
                font=("Consolas", "14"),
                fg="green3",
                bg="black",
                textvariable=string_var,
                # wrap=tk.NONE,
                # width=COLUMN_WIDTH[column_name],
                # borderwidth=0,
                # justify="left" if column_index in
                # self.left_justified_columns else "right",
                # anchor="w" if column_index in self.left_justified_columns else "e",
            )
            label.grid(
                row=row_index,
                column=column_index,
                sticky="w" if column_index in self.left_justified_columns else "e",
            )
            new_row[column_name] = Cell(label, string_var)
        self.rows.append(new_row)

    def pop_row(self) -> None:
        row = self.rows.pop()
        for column_name in self.column_names:
            row[column_name].label.destroy()

    def set_length(self, length: int) -> None:
        """"""
        current_length = len(self.rows)
        if length > current_length:
            for i in range(length - current_length):
                self.append_row()
        elif length < current_length:
            for i in range(current_length - length):
                self.pop_row()

    def update_overlay(self) -> None:
        show, title_value, new_rows = self.get_new_data()

        if show != self.shown:
            if show:
                self.show_window()
            else:
                self.hide_window()

        if title_value is None:
            self.title_cell.variable.set("")
        else:
            self.title_cell.variable.set(title_value.text)
            self.title_cell.label.configure(fg=title_value.color)

        if new_rows is not None:
            self.set_length(len(new_rows))

            for i, new_row in enumerate(new_rows):
                row = self.rows[i]
                for column_name in self.column_names:
                    row[column_name].variable.set(new_row[column_name].text)
                    row[column_name].label.configure(fg=new_row[column_name].color)

        wait_time = 10
        self.root.after(wait_time, self.update_overlay)

    def run(self) -> None:
        self.root.after(0, self.update_overlay)
        self.root.mainloop()
