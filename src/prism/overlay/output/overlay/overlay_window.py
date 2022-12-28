"""
Overlay window using tkinter

Inspired by:
https://github.com/notatallshaw/fall_guys_ping_estimate/blob/main/fgpe/overlay.py
"""
import logging
import sys
import time
import tkinter as tk
from traceback import format_exception
from types import TracebackType
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: nocover
    from prism.overlay.controller import OverlayController

logger = logging.getLogger(__name__)


class Root(tk.Tk):  # pragma: nocover
    """Root window that exits when an exception occurs in an event handler"""

    def report_callback_exception(
        self,
        __exc: type[BaseException],
        __val: BaseException,
        __tb: TracebackType | None,
    ) -> object:
        """Exit on callback exception"""
        if not issubclass(__exc, KeyboardInterrupt):
            logger.error(
                "Unhandled exception in event handler: "
                f"'''{''.join(format_exception(__exc, __val, __tb))}'''"
            )
        sys.exit(0)


class OverlayWindow:  # pragma: nocover
    """
    Overlay window using the "-topmost" property to always stay on top

    NOTE: May not appear above some fullscreen apps on Windows.
    See `prism/overlay/platform/windows.py` for more info.
    """

    def __init__(self, controller: "OverlayController", start_hidden: bool) -> None:
        """Set up window geometry to make the window an overlay"""
        self.controller = controller

        self.hide_task_id: str | None = None
        self.hide_due_at: float | None = None
        self.shown: bool = False  # Set below

        # Create a root window
        self.root = Root()

        # Window geometry
        if not self.controller.settings.disable_overrideredirect:
            self.root.overrideredirect(True)
        self.root.lift()
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", 0.8)
        self.root.configure(background="black")

        if start_hidden:
            self.hide(force=True)
        else:
            self.show(force=True)

        self.reset_position()

    def show(self, *, force: bool = False) -> None:
        """Show the window"""
        # Always cancel the scheduled hide, as any call to show indicates that the
        # user wants the window shown
        self.cancel_scheduled_hide()

        if self.shown and not force:
            # Skip actully showing the window if already shown
            return

        if self.controller.settings.hide_with_alpha:
            self.root.wm_attributes("-alpha", 0.8)
        else:
            self.root.deiconify()

        self.shown = True

    def hide(self, *, force: bool = False) -> None:
        """Hide the window"""
        # Always cancel the scheduled hide, as any call to hide means that the window
        # will already be hidden
        self.cancel_scheduled_hide()

        if not self.shown and not force:
            # Skip actully hiding the window if already hidden
            return

        if self.controller.settings.hide_with_alpha:
            self.root.wm_attributes("-alpha", 0)
        else:
            self.root.withdraw()

        self.shown = False

    def schedule_hide(self, timeout: int) -> None:
        """Schedule a hide of the window in `timeout` ms"""
        self.cancel_scheduled_hide()
        self.hide_due_at = time.monotonic() + timeout / 1000
        self.hide_task_id = self.root.after(timeout, self.hide)

    def cancel_scheduled_hide(self) -> None:
        """Cancel any existing request to hide the window"""
        if self.hide_task_id is not None:
            self.root.after_cancel(self.hide_task_id)
            self.hide_task_id = None

        self.hide_due_at = None

    @property
    def time_until_hide(self) -> float | None:
        """Return the seconds left until we hide, or None if none scheduled"""
        due = self.hide_due_at
        if due is None:
            return None

        return max(due - time.monotonic(), 0)

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
