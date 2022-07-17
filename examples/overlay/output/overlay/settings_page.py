import tkinter as tk
from typing import Callable

from examples.overlay.settings import NickValue, Settings, SettingsDict


class HypixelSection:
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section("Hypixel")
        self.frame.columnconfigure(0, weight=0)

        self.hypixel_api_key_variable = tk.StringVar()
        tk.Label(
            self.frame,
            text="API key: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=0, column=0, sticky=tk.E)
        tk.Entry(self.frame, textvariable=self.hypixel_api_key_variable).grid(
            row=0, column=1
        )

    def set(self, hypixel_api_key: str) -> None:
        """Set the state of this section"""
        self.hypixel_api_key_variable.set(hypixel_api_key)

    def get(self) -> str:
        """Get the state of this section"""
        return self.hypixel_api_key_variable.get().strip()


class AntisniperSection:
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section(
            "Antisniper", subtitle="Denicking + winstreaks"
        )
        self.frame.columnconfigure(0, weight=0)

        tk.Label(
            self.frame,
            text="Antisniper API: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=0, column=0, sticky=tk.E)

        self.use_antisniper_api_button = tk.Button(
            self.frame,
            text="",
            font=("Consolas", "12"),
            foreground="black",
            background="black",
            command=self.toggle_use_antisniper_api,
            relief="flat",
        )
        self.use_antisniper_api_button.grid(row=0, column=1)

        self.antisniper_api_key_variable = tk.StringVar()
        tk.Label(
            self.frame,
            text="API key: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=1, column=0, sticky=tk.E)
        self.antisniper_api_key_entry = tk.Entry(
            self.frame, textvariable=self.antisniper_api_key_variable
        )
        self.antisniper_api_key_entry.grid(row=1, column=1)

        # Initially toggle to get into a consistent state
        self.toggle_use_antisniper_api()

    @property
    def use_antisniper_api(self) -> bool:
        """Return the state of the toggle button"""
        return (  # type:ignore
            self.use_antisniper_api_button.config("bg")[-1] == "lime green"
        )

    def toggle_use_antisniper_api(self) -> None:
        """Toggle the state of the button"""
        if self.use_antisniper_api:
            self.use_antisniper_api_button.config(
                bg="red", activebackground="orange red", text="Disabled"
            )
            self.antisniper_api_key_entry.configure(state=tk.DISABLED)
        else:
            self.use_antisniper_api_button.config(
                bg="lime green", activebackground="lawn green", text="Enabled "
            )
            self.antisniper_api_key_entry.configure(state=tk.NORMAL)

    def set(self, use_antisniper_api: bool, antisniper_api_key: str | None) -> None:
        """Set the state of this section"""
        if self.use_antisniper_api != use_antisniper_api:
            self.toggle_use_antisniper_api()

        self.antisniper_api_key_variable.set(antisniper_api_key or "")

    def get(self) -> tuple[bool, str | None]:
        """Get the state of this section"""
        raw_antisniper_api_key = self.antisniper_api_key_variable.get().strip()
        return self.use_antisniper_api, raw_antisniper_api_key or None


class SettingsPage:
    """Settings page for the overlay"""

    def __init__(
        self,
        parent: tk.Misc,
        close_settings_page: Callable[[], None],
        update_settings: Callable[[SettingsDict], None],
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

        self.hypixel_section = HypixelSection(self)
        self.antisniper_section = AntisniperSection(self)

    def make_section(
        self, section_header: str, subtitle: str | None = None
    ) -> tk.Frame:
        """Make a settings section with a header and a frame for the settings"""
        label = tk.Label(
            self.settings_frame,
            text=section_header,
            font=("Consolas", "14"),
            foreground="white",
            background="black",
        )
        label.pack(side=tk.TOP, pady=(5, 0))

        if subtitle is not None:
            tk.Label(
                self.settings_frame,
                text=subtitle,
                font=("Consolas", "10"),
                foreground="white",
                background="black",
            ).pack(side=tk.TOP)

        section_frame = tk.Frame(self.settings_frame, background="black")
        section_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0, 10))

        return section_frame

    def set_content(self, settings: Settings) -> None:
        """Set the content of the page to the values from `settings`"""
        with settings.mutex:
            self.hypixel_section.set(settings.hypixel_api_key)

            self.antisniper_section.set(
                settings.use_antisniper_api, settings.antisniper_api_key
            )

    def on_save(self) -> None:
        """Handle the user saving their settings"""
        hypixel_api_key = self.hypixel_section.get()
        use_antisniper_api, antisniper_api_key = self.antisniper_section.get()
        known_nicks: dict[str, NickValue] = {}

        self.update_settings(
            SettingsDict(
                hypixel_api_key=hypixel_api_key,
                antisniper_api_key=antisniper_api_key,
                use_antisniper_api=use_antisniper_api,
                known_nicks=known_nicks,
            )
        )

        # Go back to the main content
        self.close_settings_page()
