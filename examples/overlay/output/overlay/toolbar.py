import math
import tkinter as tk
from collections.abc import Callable

from examples.overlay import VERSION_STRING
from examples.overlay.output.overlay.overlay_window import OverlayWindow


class Toolbar:
    """Toolbar for the overlay"""

    def __init__(
        self,
        parent: tk.Misc,
        window: OverlayWindow,
        close_callback: Callable[[], None],
        minimize_callback: Callable[[], None],
        fullscreen_callback: Callable[[], None] | None,
    ) -> None:
        """Set up a frame containing the toolbar for the overlay"""
        self.window = window

        self.frame = tk.Frame(parent, background="black")

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

        self.hide_countdown_label = tk.Label(
            self.frame,
            text="",
            font=("Consolas", "10"),
            foreground="white",
            background="black",
        )
        self.hide_countdown_label.pack(side=tk.RIGHT, padx=(0, 5))

        self.update_hide_countdown()

    def update_hide_countdown(self) -> None:
        time_until = self.window.time_until_hide
        if time_until is None:
            self.hide_countdown_label.configure(text="")
        else:
            self.hide_countdown_label.configure(text=f"Hiding: {math.ceil(time_until)}")
        self.window.root.after(100, self.update_hide_countdown)
