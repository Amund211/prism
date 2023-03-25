import logging
import threading
import tkinter as tk
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Generic, Literal, assert_never

from prism.overlay.controller import OverlayController
from prism.overlay.keybinds import SpecialKey, create_pynput_normalizer
from prism.overlay.output.overlay.main_content import MainContent
from prism.overlay.output.overlay.overlay_window import OverlayWindow
from prism.overlay.output.overlay.set_nickname_page import SetNicknamePage
from prism.overlay.output.overlay.settings_page import SettingsPage
from prism.overlay.output.overlay.toolbar import Toolbar
from prism.overlay.output.overlay.utils import ColumnKey, InfoCellValue, OverlayRowData

if TYPE_CHECKING:  # pragma: nocover
    import pynput

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
            [], tuple[bool, list[InfoCellValue], list[OverlayRowData[ColumnKey]] | None]
        ],
        update_available_event: threading.Event,
        poll_interval: int,
        hide_pause_ms: int = 5000,
    ):
        """Set up content in an OverlayWindow"""
        self.controller = controller
        self.poll_interval = poll_interval
        self.get_new_data = get_new_data
        self.update_available_event = update_available_event
        self.hide_pause_ms = hide_pause_ms

        # Set should_show so the window remains in the desired state based on
        # start_hidden until a falling/rising edge in show from get_new_data
        # Also set last_new_rows so we don't miss the first update
        self.should_show: bool
        self.last_new_rows: list[OverlayRowData[ColumnKey]] | None
        self.should_show, _, self.last_new_rows = self.get_new_data()

        self.current_page: Page = "main"

        # Layout
        self.window = OverlayWindow(controller=controller, start_hidden=start_hidden)
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

        # Set up the tab listener
        self.tab_pressed = False
        self.listener: "pynput.keyboard.Listener | None" = None
        if self.controller.settings.show_on_tab:
            self.setup_tab_listener()

        # Update geometry and stuff, if necessary
        self.window.root.update_idletasks()

    def setup_tab_listener(self, *, restart: bool = False) -> None:
        if self.listener is not None:
            if restart:
                # Stop the current listener and start a new one
                self.stop_tab_listener()
            else:
                return

        try:
            import pynput
        except Exception:
            logger.exception("Failed to import pynput")

            # Disable show on tab since it won't work
            with self.controller.settings.mutex:
                self.controller.settings.show_on_tab = False
                self.controller.settings.flush_to_disk()
            logger.warning("Disabled show on tab due to error loading pynput")

            return

        normalize = create_pynput_normalizer()

        # The user-defined hotkey for show on tab
        tab_hotkey = self.controller.settings.show_on_tab_keybind

        if (
            isinstance(tab_hotkey, SpecialKey)
            and tab_hotkey.name == "tab"
            and tab_hotkey.vk is None
        ):
            # This is a special sentinel value used to specify <tab>
            tab_hotkey_with_vk = normalize(pynput.keyboard.Key.tab)
            if tab_hotkey_with_vk is None:
                logger.warning("Failed to get vk for <tab>")
                return

            tab_hotkey = tab_hotkey_with_vk

            with self.controller.settings.mutex:
                self.controller.settings.show_on_tab_keybind = tab_hotkey
                self.controller.settings.flush_to_disk()
                logger.info(f"Updated settings with vk for <tab> {tab_hotkey}")

        PynputKeyType = pynput.keyboard.Key | pynput.keyboard.KeyCode | None

        def on_press(pynput_key: PynputKeyType) -> None:
            if self.tab_pressed:
                return

            key = normalize(pynput_key)
            if key == tab_hotkey:
                self.tab_pressed = True
                self.window.show()

        def on_release(pynput_key: PynputKeyType) -> None:
            if not self.tab_pressed:
                return

            key = normalize(pynput_key)
            if key == tab_hotkey:
                self.tab_pressed = False
                if not self.should_show and self.current_page == "main":
                    self.window.hide()

        self.tab_pressed = False

        self.listener = pynput.keyboard.Listener(
            on_press=on_press, on_release=on_release
        )
        self.listener.start()

    def stop_tab_listener(self) -> None:
        if self.listener is None:
            return

        self.listener.stop()
        self.listener = None

        self.tab_pressed = False

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
            self.settings_page.on_close()
            self.settings_page.frame.pack_forget()
        elif self.current_page == "set_nickname":
            self.set_nickname_page.frame.pack_forget()
        else:
            assert_never(self.current_page)

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
            assert_never(self.current_page)

        self.current_page = new_page

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
                if not self.tab_pressed:
                    # Only schedule hide if the user is not holding tab
                    self.window.schedule_hide(timeout_ms=self.hide_pause_ms)

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
