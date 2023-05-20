import math
import os
import sys
import tkinter as tk
from collections.abc import Callable
from typing import TYPE_CHECKING

from prism import VERSION_STRING
from prism.overlay.controller import OverlayController

if TYPE_CHECKING:  # pragma: nocover
    from prism.overlay.output.overlay.stats_overlay import StatsOverlay

if os.name == "nt":  # pragma: nocover
    from prism.overlay.platform.windows import toggle_fullscreen

    FULLSCREEN_CALLBACK: Callable[[], None] | None = toggle_fullscreen
else:  # pragma: nocover
    FULLSCREEN_CALLBACK = None


class Toolbar:  # pragma: nocover
    """Toolbar for the overlay"""

    def __init__(
        self,
        parent: tk.Misc,
        overlay: "StatsOverlay",
        controller: OverlayController,
    ) -> None:
        """Set up a frame containing the toolbar for the overlay"""
        self.overlay = overlay

        self.frame = tk.Frame(parent, background="black")
        self.register_grab_handler(self.frame)

        grip_label = tk.Label(
            self.frame,
            text="::",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            highlightthickness=1,
        )
        grip_label.pack(side=tk.LEFT, padx=(3, 5))

        self.register_grab_handler(grip_label)
        grip_label.bind("<Double-Button-1>", self.overlay.window.reset_position)
        grip_label.configure(cursor="hand2")

        def toggle_settings_page() -> None:
            if self.overlay.current_page == "settings":
                self.overlay.switch_page("main")
            else:
                self.overlay.switch_page("settings")

        # Settings button
        settings_button = tk.Button(
            self.frame,
            text="⚙",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            highlightthickness=0,
            command=toggle_settings_page,
            relief="flat",
            cursor="hand2",
        )
        settings_button.pack(side=tk.LEFT)

        if FULLSCREEN_CALLBACK is not None:
            # Fullscreen button
            fullscreen_button = tk.Button(
                self.frame,
                text="Fullscreen",
                font=("Consolas", "14"),
                foreground="white",
                background="black",
                highlightthickness=0,
                command=FULLSCREEN_CALLBACK,
                relief="flat",
                cursor="hand2",
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
            command=sys.exit,
            relief="flat",
            cursor="hand2",
        )
        close_button.pack(side=tk.RIGHT)

        # Minimize button
        def minimize() -> None:
            controller.wants_shown = False

            self.overlay.window.hide()

        minimize_button = tk.Button(
            self.frame,
            text="-",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            highlightthickness=0,
            command=minimize,
            relief="flat",
            cursor="hand2",
        )
        minimize_button.pack(side=tk.RIGHT)

        version_label = tk.Label(
            self.frame,
            text=f"Prism {VERSION_STRING}",
            font=("Consolas", "10"),
            foreground="white",
            background="black",
        )
        version_label.pack(side=tk.RIGHT, padx=(0, 5))
        self.register_grab_handler(version_label)

        self.hide_countdown_label = tk.Label(
            self.frame,
            text="",
            font=("Consolas", "10"),
            foreground="white",
            background="black",
        )
        self.hide_countdown_label.pack(side=tk.RIGHT, padx=(0, 5))
        self.register_grab_handler(self.hide_countdown_label)

        self.update_hide_countdown()

    def register_grab_handler(self, widget: tk.Frame | tk.Label) -> None:
        """Register the widget to enable dragging the window"""
        widget.bind("<ButtonPress-1>", self.overlay.window.start_move)
        widget.bind("<B1-Motion>", self.overlay.window.do_move)
        widget.bind("<ButtonRelease-1>", self.overlay.window.stop_move)
        widget.configure(cursor="fleur")

    def update_hide_countdown(self) -> None:
        time_until = self.overlay.window.time_until_hide
        if time_until is None:
            self.hide_countdown_label.configure(text="")
        else:
            self.hide_countdown_label.configure(text=f"Hiding: {math.ceil(time_until)}")
        self.overlay.window.root.after(100, self.update_hide_countdown)
