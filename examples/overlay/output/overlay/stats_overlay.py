import tkinter as tk
from collections.abc import Callable, Sequence
from typing import Generic, Literal

from examples.overlay.output.overlay.main_content import MainContent
from examples.overlay.output.overlay.overlay_window import OverlayWindow
from examples.overlay.output.overlay.settings_page import SettingsPage
from examples.overlay.output.overlay.toolbar import Toolbar
from examples.overlay.output.overlay.utils import CellValue, ColumnKey, OverlayRow

Page = Literal["settings", "main"]


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

        self.current_page: Page = "main"

        self.window = OverlayWindow(start_hidden=start_hidden)

        # Frame for the current page
        self.page_frame = tk.Frame(self.window.root, background="black")
        self.page_frame.pack(side=tk.BOTTOM, fill=tk.BOTH)

        # Add the main content
        self.main_content = MainContent(
            parent=self.page_frame,
            column_order=column_order,
            column_names=column_names,
            left_justified_columns=left_justified_columns,
        )
        self.main_content.frame.pack(side=tk.TOP, fill=tk.BOTH)

        def open_settings_page() -> None:
            """Hide main content and open settings"""
            if self.current_page != "main":
                return
            # Don't hide while the user is editing their settings
            self.window.cancel_scheduled_hide()

            self.current_page = "settings"
            self.main_content.frame.pack_forget()
            self.settings_page.frame.pack(side=tk.TOP, fill=tk.BOTH)

        def close_settings_page() -> None:
            """Hide settings and open main content"""
            if self.current_page != "settings":
                return
            self.current_page = "main"
            self.settings_page.frame.pack_forget()
            self.main_content.frame.pack(side=tk.TOP, fill=tk.BOTH)

        # Add the settings page
        self.settings_page = SettingsPage(
            self.page_frame,
            close_settings_page=close_settings_page,
            update_settings=print,
        )

        # Add the toolbar
        self.toolbar = Toolbar(
            parent=self.window.root,
            window=self.window,
            close_callback=close_callback,
            minimize_callback=minimize_callback,
            settings_callback=open_settings_page,
            fullscreen_callback=fullscreen_callback,
        )
        self.toolbar.frame.pack(side=tk.TOP, expand=True, fill=tk.X)

        self.window.root.update_idletasks()

    def update_overlay(self) -> None:
        """Get new data to be displayed and display it"""
        show, info_cells, new_rows = self.get_new_data()

        # Show or hide the window if the desired state is different from the stored
        if show != self.should_show:

            if show:
                self.should_show = show
                self.window.show()
            elif self.current_page == "main":  # Only hide when we are on the main page
                self.should_show = show
                self.window.schedule_hide(self.hide_pause)

        # Only update the window if it's shown
        if self.window.shown and self.current_page == "main":
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
