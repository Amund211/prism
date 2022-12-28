import tkinter as tk
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from prism.overlay.behaviour import update_settings
from prism.overlay.controller import OverlayController
from prism.overlay.settings import NickValue, Settings, SettingsDict

if TYPE_CHECKING:  # pragma: nocover
    from prism.overlay.output.overlay.stats_overlay import StatsOverlay
    from prism.overlay.output.overlay.utils import ColumnKey


class ToggleButton:  # pragma: nocover
    DISABLED_CONFIG = {
        "text": "Disabled",
        "bg": "red",
        "activebackground": "orange red",
    }
    ENABLED_CONFIG = {
        "text": "Enabled ",
        "bg": "lime green",
        "activebackground": "lawn green",
    }

    def __init__(
        self,
        frame: tk.Frame,
        toggle_callback: Callable[[bool], Any] = lambda enabled: None,
    ) -> None:
        self.toggle_callback = toggle_callback

        self.button = tk.Button(
            frame,
            text="",
            font=("Consolas", "12"),
            foreground="black",
            background="black",
            command=self.toggle,
            relief="flat",
        )

        # Initially toggle to get into a consistent state
        self.toggle()

    @property
    def enabled(self) -> bool:
        """Return the state of the toggle button"""
        return self.button.config("bg")[-1] == "lime green"  # type:ignore

    def toggle(self) -> None:
        """Toggle the state of the button"""
        self.button.config(
            **(self.DISABLED_CONFIG if self.enabled else self.ENABLED_CONFIG)
        )
        self.toggle_callback(self.enabled)

    def set(self, enabled: bool) -> None:
        """Set the enabled state of the toggle button"""
        if self.enabled != enabled:
            self.toggle()


class HypixelSection:  # pragma: nocover
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


class AntisniperSection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section(
            "Antisniper", subtitle="Denicking + winstreaks"
        )
        self.frame.columnconfigure(0, weight=0)

        info_label = tk.Label(
            self.frame,
            text=(
                "Visit antisniper.net, join (and STAY in) the discord server and "
                "follow the instructions on how to verify to get an API key. "
                "This service is not affiliated, and use is at your own risk."
            ),
            font=("Consolas", "10"),
            foreground="white",
            background="black",
        )
        info_label.bind("<Configure>", lambda e: info_label.config(wraplength=400))
        info_label.grid(row=0, columnspan=2)

        tk.Label(
            self.frame,
            text="Antisniper API: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=1, column=0, sticky=tk.E)

        # NOTE: We make this early so it exists in the callback for the toggle
        self.antisniper_api_key_variable = tk.StringVar()
        self.antisniper_api_key_entry = tk.Entry(
            self.frame, textvariable=self.antisniper_api_key_variable
        )

        self.use_antisniper_api_toggle = ToggleButton(
            self.frame,
            lambda enabled: self.antisniper_api_key_entry.configure(
                state=tk.NORMAL if enabled else tk.DISABLED
            ),
        )
        self.use_antisniper_api_toggle.button.grid(row=1, column=1)

        tk.Label(
            self.frame,
            text="API key: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=2, column=0, sticky=tk.E)

        self.antisniper_api_key_entry.grid(row=2, column=1)

    def set(self, use_antisniper_api: bool, antisniper_api_key: str | None) -> None:
        """Set the state of this section"""
        self.use_antisniper_api_toggle.set(use_antisniper_api)

        self.antisniper_api_key_variable.set(antisniper_api_key or "")

    def get(self) -> tuple[bool, str | None]:
        """Get the state of this section"""
        raw_antisniper_api_key = self.antisniper_api_key_variable.get().strip()
        return self.use_antisniper_api_toggle.enabled, raw_antisniper_api_key or None


class LocalSettingsSection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section("Local Settings")
        self.frame.columnconfigure(0, weight=0)

        tk.Label(
            self.frame,
            text="Show overlay on tab: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=1, column=0, sticky=tk.E)
        self.tab_to_show_toggle = ToggleButton(self.frame)
        self.tab_to_show_toggle.button.grid(row=1, column=1)

    def set(self, tab_to_show: bool) -> None:
        """Set the state of this section"""
        self.tab_to_show_toggle.set(tab_to_show)

    def get(self) -> bool:
        """Get the state of this section"""
        return self.tab_to_show_toggle.enabled


class GraphicsSection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.parent = parent
        self.frame = parent.make_section("Graphics")
        self.frame.columnconfigure(0, weight=0)

        self.alpha_hundredths_variable = tk.IntVar(value=80)
        self.alpha_hundredths_variable.trace_add("write", self.set_window_alpha)
        tk.Label(
            self.frame,
            text="Alpha: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=0, column=0, sticky=tk.E)
        tk.Scale(
            self.frame,
            from_=10,
            to=100,
            orient=tk.HORIZONTAL,
            length=200,
            foreground="white",
            background="black",
            variable=self.alpha_hundredths_variable,
        ).grid(row=0, column=1)

    def set_window_alpha(self, *args: Any, **kwargs: Any) -> None:
        self.parent.overlay.window.set_alpha_hundredths(
            self.clamp_alpha(self.alpha_hundredths_variable.get())
        )

    def clamp_alpha(self, alpha_hundredths: int) -> int:
        """Clamp the alpha_hundredths to a valid range"""
        return min(100, max(10, alpha_hundredths))

    def set(self, alpha_hundredths: int) -> None:
        """Set the state of this section"""
        self.alpha_hundredths_variable.set(self.clamp_alpha(alpha_hundredths))

    def get(self) -> int:
        """Get the state of this section"""
        return self.clamp_alpha(self.alpha_hundredths_variable.get())


class SettingsPage:  # pragma: nocover
    """Settings page for the overlay"""

    def __init__(
        self,
        parent: tk.Misc,
        overlay: "StatsOverlay[ColumnKey]",
        controller: OverlayController,
    ) -> None:
        """Set up a frame containing the settings page for the overlay"""
        self.frame = tk.Frame(parent, background="black")

        self.overlay = overlay
        self.controller = controller

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
            command=self.on_cancel,
            relief="flat",
        )
        cancel_button.pack(side=tk.RIGHT, padx=(0, 5))

        # A frame for the settings
        self.settings_frame = tk.Frame(self.frame, background="black")
        self.settings_frame.pack(side=tk.TOP, fill=tk.BOTH)

        self.hypixel_section = HypixelSection(self)
        self.antisniper_section = AntisniperSection(self)
        self.local_settings_section = LocalSettingsSection(self)
        self.graphics_section = GraphicsSection(self)

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
            self.local_settings_section.set(settings.show_on_tab)
            self.graphics_section.set(settings.alpha_hundredths)

    def on_cancel(self) -> None:
        """Handle the user clicking cancel"""
        # Reset alpha in case the user changed the slider
        self.overlay.window.set_alpha_hundredths(
            self.controller.settings.alpha_hundredths
        )

        self.overlay.switch_page("main")

    def on_save(self) -> None:
        """Handle the user saving their settings"""
        hypixel_api_key = self.hypixel_section.get()
        use_antisniper_api, antisniper_api_key = self.antisniper_section.get()
        known_nicks: dict[str, NickValue] = {}
        # TODO: Add section to edit known nicks
        with self.controller.settings.mutex:
            known_nicks = self.controller.settings.known_nicks.copy()
        show_on_tab = self.local_settings_section.get()

        # "Secret" settings, not editable in the GUI
        disable_overrideredirect = self.controller.settings.disable_overrideredirect
        hide_with_alpha = self.controller.settings.hide_with_alpha

        alpha_hundredths = self.graphics_section.get()

        new_settings = SettingsDict(
            hypixel_api_key=hypixel_api_key,
            antisniper_api_key=antisniper_api_key,
            use_antisniper_api=use_antisniper_api,
            known_nicks=known_nicks,
            show_on_tab=show_on_tab,
            disable_overrideredirect=disable_overrideredirect,
            hide_with_alpha=hide_with_alpha,
            alpha_hundredths=alpha_hundredths,
        )

        with self.controller.settings.mutex:
            update_settings(new_settings, self.controller)

        # Setup/stop tab listener
        # NOTE: This happens outside of update_settings, so care must be taken if
        #       update_settings is called somewhere else to also setup/stop the listener
        if self.controller.settings.show_on_tab:
            self.overlay.setup_tab_listener()
        else:
            self.overlay.stop_tab_listener()

        # Update alpha
        self.overlay.window.set_alpha_hundredths(alpha_hundredths)

        # Go back to the main content
        self.overlay.switch_page("main")
