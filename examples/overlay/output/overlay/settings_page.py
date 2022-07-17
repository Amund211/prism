import tkinter as tk
from typing import Callable

from examples.overlay.settings import Settings


class SettingsPage:
    """Settings page for the overlay"""

    def __init__(
        self,
        parent: tk.Misc,
        close_settings_page: Callable[[], None],
        update_settings: Callable[[Settings], None],
    ) -> None:
        """Set up a frame containing the settings page for the overlay"""
        self.frame = tk.Frame(parent, background="black")

        self.update_settings = update_settings
        self.close_settings_page = close_settings_page

        # Frame for the save and cancel buttons
        self.controls_frame = tk.Frame(self.frame, background="black")
        self.controls_frame.pack(
            side=tk.BOTTOM, expand=True, fill=tk.X, padx=5, pady=(0, 3)
        )

        # Save button
        save_button = tk.Button(
            self.controls_frame,
            text="Save",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            command=self.on_save,
            relief="flat",
        )
        save_button.pack(side=tk.RIGHT)

        # Minimize button
        cancel_button = tk.Button(
            self.controls_frame,
            text="Cancel",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            command=self.close_settings_page,
            relief="flat",
        )
        cancel_button.pack(side=tk.RIGHT, padx=(0, 5))

        # A frame for the settings
        self.settings_frame = tk.Frame(self.frame, background="black")
        self.settings_frame.pack(side=tk.TOP, fill=tk.BOTH)

        for header in ("Hypixel", "Antisniper", "Nicknames"):
            self.make_section(header)

    def make_section(self, section_header: str) -> tk.Frame:
        """Make a settings section with a header and a frame for the settings"""
        label = tk.Label(
            self.settings_frame,
            text=section_header,
            font=("Consolas", "14"),
            foreground="white",
            background="black",
        )
        label.pack(side=tk.TOP, pady=(5, 0))

        section_frame = tk.Frame(self.settings_frame, background="black")
        section_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        return section_frame

    def on_save(self) -> None:
        """Handle the user saving their settings"""
        # TODO: Read the variables to create a new settings object
        # self.update_settings(new_settings)
        # Go back to the main content
        self.close_settings_page()
