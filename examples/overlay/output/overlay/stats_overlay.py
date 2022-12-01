import logging
import tkinter as tk
from collections.abc import Callable, Sequence
from typing import Generic, Literal

import pynput

from examples.overlay.controller import OverlayController
from examples.overlay.output.overlay.main_content import MainContent
from examples.overlay.output.overlay.overlay_window import OverlayWindow
from examples.overlay.output.overlay.set_nickname_page import SetNicknamePage
from examples.overlay.output.overlay.settings_page import SettingsPage
from examples.overlay.output.overlay.toolbar import Toolbar
from examples.overlay.output.overlay.utils import CellValue, ColumnKey, OverlayRowData
from examples.overlay import settings

logger = logging.getLogger(__name__)

Page = Literal["settings", "main", "set_nickname"]


class StatsOverlay(Generic[ColumnKey]):  # pragma: nocover
    """Show bedwars stats in an overlay"""

    def __init__(
        self,
        start_hidden: bool,
        column_order: Sequence[ColumnKey],
        column_names: dict[ColumnKey, str],
        left_justified_columns: set[int],
        controller: OverlayController,
        get_new_data: Callable[
            [], tuple[bool, list[CellValue], list[OverlayRowData[ColumnKey]] | None]
        ],
        poll_interval: int,
        hide_pause: int = 5000,
    ):
        """Set up content in an OverlayWindow"""

        # Will already be populated
        self.setting: settings.Settings = settings.get_settings(None, None)

        self.start_tab_listener()

        self.controller = controller
        self.poll_interval = poll_interval
        self.get_new_data = get_new_data
        self.hide_pause = hide_pause

        self.should_show = False

        self.last_new_rows: list[OverlayRowData[ColumnKey]] | None = None

        # Set should_show so the window remains in the desired state based on
        # start_hidden until a falling/rising edge in show from get_new_data
        # Also set last_new_rows so we don't miss the first update
        self.should_show, _, self.last_new_rows = self.get_new_data()

        self.current_page: Page = "main"

        self.window = OverlayWindow(start_hidden=start_hidden)
        self.controller = controller

        # Frame for the current page
        self.page_frame = tk.Frame(self.window.root, background="black")
        self.page_frame.pack(side=tk.BOTTOM, fill=tk.BOTH)

        # Add the main content
        self.main_content = MainContent(
            parent=self.page_frame,
            overlay=self,
            column_order=column_order,
            column_names=column_names,
            left_justified_columns=left_justified_columns,
        )
        self.main_content.frame.pack(side=tk.TOP, fill=tk.BOTH)

        # Add the settings page
        self.settings_page = SettingsPage(self.page_frame, self, controller)

        # Add the set nickname page
        self.set_nickname_page = SetNicknamePage(self.page_frame, self, controller)

        # Add the toolbar
        self.toolbar = Toolbar(
            parent=self.window.root, overlay=self, controller=self.controller
        )
        self.toolbar.frame.pack(side=tk.TOP, expand=True, fill=tk.X)

        self.window.root.update_idletasks()

    def start_tab_listener(self):
        self.tab_pressed = False

        def set_tab_pressed(key):
            with (self.setting.mutex):
                if(not self.setting.show_on_tab):
                    return
            if key == pynput.keyboard.Key.tab:  
                self.tab_pressed = True

        listener = pynput.keyboard.Listener(on_press=set_tab_pressed)
        listener.start()


    def switch_page(self, new_page: Page) -> None:
        """Switch to the given page"""
        if self.current_page == new_page:
            logger.warning(f"Switching from {new_page} to itself")
            return

        # Don't hide while the user is interacting with the GUI
        self.window.cancel_scheduled_hide()

        # Unmount current content
        if self.current_page == "main":
            self.main_content.frame.pack_forget()
        elif self.current_page == "settings":
            self.settings_page.frame.pack_forget()
        elif self.current_page == "set_nickname":
            self.set_nickname_page.frame.pack_forget()
        else:
            # For typing assert unreached
            return False

        # Mount new content
        if new_page == "main":
            self.main_content.frame.pack(side=tk.TOP, fill=tk.BOTH)
        elif new_page == "settings":
            self.settings_page.set_content(self.controller.settings)
            self.settings_page.frame.pack(side=tk.TOP, fill=tk.BOTH)
        elif new_page == "set_nickname":
            # NOTE: caller must update the content
            self.set_nickname_page.frame.pack(side=tk.TOP, fill=tk.BOTH)
        else:
            # For typing assert unreached
            return False

        self.current_page = new_page

    def update_overlay(self) -> None:
        """Get new data to be displayed and display it"""
        show, info_cells, new_rows = self.get_new_data()

        # Show or hide the window if the desired state is different from the stored
        if self.tab_pressed:
            self.tab_pressed = False
            show = True

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
