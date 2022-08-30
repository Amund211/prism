import tkinter as tk
from collections.abc import Callable, Sequence
from typing import Generic

from examples.overlay.output.overlay.main_content import MainContent
from examples.overlay.output.overlay.overlay_window import OverlayWindow
from examples.overlay.output.overlay.toolbar import Toolbar
from examples.overlay.output.overlay.utils import CellValue, ColumnKey, OverlayRow


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

        self.should_show = not start_hidden

        self.last_new_rows: list[OverlayRow[ColumnKey]] | None = None

        self.window = OverlayWindow(start_hidden=start_hidden)

        # Add the toolbar
        self.toolbar = Toolbar(
            parent=self.window.root,
            window=self.window,
            close_callback=close_callback,
            minimize_callback=minimize_callback,
            fullscreen_callback=fullscreen_callback,
        )
        self.toolbar.frame.pack(side=tk.TOP, expand=True, fill=tk.X)

        # Add the main content
        self.main_content = MainContent(
            parent=self.window.root,
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
        if show != self.should_show:
            self.should_show = show

            if show:
                self.window.show()
            else:
                self.window.schedule_hide(self.hide_pause)

        # Only update the window if it's shown
        if self.window.shown:
            # Update the table with the new rows
            # Fall back to the last new rows from when the table was hidden
            self.main_content.update_content(
                info_cells, new_rows if new_rows is not None else self.last_new_rows
            )
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
