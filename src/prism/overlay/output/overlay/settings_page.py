import logging
import tkinter as tk
from typing import TYPE_CHECKING, Any

from prism.overlay.behaviour import update_settings
from prism.overlay.controller import OverlayController
from prism.overlay.keybinds import Key
from prism.overlay.output.cells import (
    ALL_COLUMN_NAMES_ORDERED,
    ColumnName,
    str_is_column_name,
)
from prism.overlay.output.overlay.gui_components import KeybindSelector, ToggleButton
from prism.overlay.settings import NickValue, Settings, SettingsDict
from prism.overlay.threading import UpdateCheckerOneShotThread

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: nocover
    from prism.overlay.output.overlay.stats_overlay import StatsOverlay


class GeneralSettingSection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section("General Settings")
        self.frame.columnconfigure(0, weight=0)

        tk.Label(
            self.frame,
            text="Autodenick teammates: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=0, column=0, sticky=tk.E)
        self.autodenick_teammates_toggle = ToggleButton(self.frame)
        self.autodenick_teammates_toggle.button.grid(row=0, column=1)

        tk.Label(
            self.frame,
            text="Autoselect logfile: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=1, column=0, sticky=tk.E)
        self.autoselect_logfile_toggle = ToggleButton(self.frame)
        self.autoselect_logfile_toggle.button.grid(row=1, column=1)

        tk.Label(
            self.frame,
            text="Show overlay on tab: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=2, column=0, sticky=tk.E)
        self.show_on_tab_toggle = ToggleButton(self.frame)
        self.show_on_tab_toggle.button.grid(row=2, column=1)

        tk.Label(
            self.frame,
            text="Show on tab hotkey: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=3, column=0, sticky=tk.E)
        self.show_on_tab_keybind_selector = KeybindSelector(
            self.frame, overlay=parent.overlay
        )
        self.show_on_tab_keybind_selector.button.grid(row=3, column=1)

        tk.Label(
            self.frame,
            text="Check for overlay version updates: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=4, column=0, sticky=tk.E)
        self.check_for_updates_toggle = ToggleButton(self.frame)
        self.check_for_updates_toggle.button.grid(row=4, column=1)

    def set(
        self,
        autodenick_teammates: bool,
        autoselect_logfile: bool,
        show_on_tab: bool,
        show_on_tab_keybind: Key,
        check_for_updates: bool,
    ) -> None:
        """Set the state of this section"""
        self.autodenick_teammates_toggle.set(autodenick_teammates)
        self.autoselect_logfile_toggle.set(autoselect_logfile)
        self.show_on_tab_toggle.set(show_on_tab)
        self.show_on_tab_keybind_selector.set_key(show_on_tab_keybind)
        self.check_for_updates_toggle.set(check_for_updates)

    def get(self) -> tuple[bool, bool, bool, Key, bool]:
        """Get the state of this section"""
        return (
            self.autodenick_teammates_toggle.enabled,
            self.autoselect_logfile_toggle.enabled,
            self.show_on_tab_toggle.enabled,
            self.show_on_tab_keybind_selector.key,
            self.check_for_updates_toggle.enabled,
        )


class DisplaySection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section(
            "Display Settings", "Customize the stats table display"
        )
        self.frame.columnconfigure(0, weight=0)

        tk.Label(
            self.frame,
            text="Sort order: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=0, column=0, sticky=tk.E)

        self.sort_order_variable = tk.StringVar(value="")
        self.sort_order_menu = tk.OptionMenu(
            self.frame, self.sort_order_variable, *ALL_COLUMN_NAMES_ORDERED
        )
        self.sort_order_menu.grid(row=0, column=1)

        tk.Label(
            self.frame,
            text="Hide dead players: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=1, column=0, sticky=tk.E)
        self.hide_dead_players_toggle = ToggleButton(self.frame)
        self.hide_dead_players_toggle.button.grid(row=1, column=1)

    def set(self, sort_order: ColumnName, hide_dead_players: bool) -> None:
        """Set the state of this section"""
        self.sort_order_variable.set(sort_order)
        self.hide_dead_players_toggle.set(hide_dead_players)

    def get(self, fallback_sort_order: ColumnName) -> tuple[ColumnName, bool]:
        """Get the state of this section"""
        sort_order: str | ColumnName = self.sort_order_variable.get()

        if not str_is_column_name(sort_order):
            logger.error(
                f"Tried saving invalid sort order {sort_order} "
                f"Falling back to {fallback_sort_order}."
            )
            sort_order = fallback_sort_order

        return sort_order, self.hide_dead_players_toggle.enabled


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
        self.hypixel_api_key_entry = tk.Entry(
            self.frame, show="*", textvariable=self.hypixel_api_key_variable
        )
        self.hypixel_api_key_entry.grid(row=0, column=1, sticky=tk.W + tk.E)
        self.frame.columnconfigure(1, weight=1)

        tk.Button(
            self.frame,
            text="SHOW",
            font=("Consolas", "10"),
            foreground="black",
            background="gray",
            activebackground="red",
            command=lambda: self.hypixel_api_key_entry.config(show=""),
            relief="flat",
            cursor="hand2",
        ).grid(row=0, column=2, padx=(5, 0))

    def set(self, hypixel_api_key: str) -> None:
        """Set the state of this section"""
        self.hypixel_api_key_entry.config(show="*")
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

        self.use_antisniper_api_toggle = ToggleButton(
            self.frame,
            toggle_callback=self.set_key_entry_state,
        )
        self.use_antisniper_api_toggle.button.grid(row=1, column=1)

        tk.Label(
            self.frame,
            text="API key: ",
            font=("Consolas", "12"),
            foreground="white",
            background="black",
        ).grid(row=2, column=0, sticky=tk.E)

        self.antisniper_api_key_variable = tk.StringVar()
        self.antisniper_api_key_entry = tk.Entry(
            self.frame, show="*", textvariable=self.antisniper_api_key_variable
        )
        self.set_key_entry_state(self.use_antisniper_api_toggle.enabled)

        self.antisniper_api_key_entry.grid(row=2, column=1, sticky=tk.W + tk.E)
        self.frame.columnconfigure(1, weight=1)

        tk.Button(
            self.frame,
            text="SHOW",
            font=("Consolas", "10"),
            foreground="black",
            background="gray",
            activebackground="red",
            command=lambda: self.antisniper_api_key_entry.config(show=""),
            relief="flat",
            cursor="hand2",
        ).grid(row=2, column=2, padx=(5, 0))

    def set(self, use_antisniper_api: bool, antisniper_api_key: str | None) -> None:
        """Set the state of this section"""
        self.use_antisniper_api_toggle.set(use_antisniper_api)

        self.antisniper_api_key_entry.config(show="*")
        self.antisniper_api_key_variable.set(antisniper_api_key or "")

    def get(self) -> tuple[bool, str | None]:
        """Get the state of this section"""
        raw_antisniper_api_key = self.antisniper_api_key_variable.get().strip()
        return self.use_antisniper_api_toggle.enabled, raw_antisniper_api_key or None

    def set_key_entry_state(self, enabled: bool) -> None:
        """Enable the key entry if the api is enabled, disable if disabled"""
        self.antisniper_api_key_entry.configure(
            state=tk.NORMAL if enabled else tk.DISABLED
        )


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
        overlay: "StatsOverlay",
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
            cursor="hand2",
        )
        save_button.pack(side=tk.RIGHT)

        # Cancel button
        cancel_button = tk.Button(
            self.controls_frame,
            text="Cancel",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            command=lambda: self.overlay.switch_page("main"),
            relief="flat",
            cursor="hand2",
        )
        cancel_button.pack(side=tk.RIGHT, padx=(0, 5))

        # A frame for the settings
        self.settings_frame = tk.Frame(self.frame, background="black")
        self.settings_frame.pack(side=tk.TOP, fill=tk.BOTH)

        self.general_settings_section = GeneralSettingSection(self)
        self.display_section = DisplaySection(self)
        self.hypixel_section = HypixelSection(self)
        self.antisniper_section = AntisniperSection(self)
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
            self.general_settings_section.set(
                autodenick_teammates=settings.autodenick_teammates,
                autoselect_logfile=settings.autoselect_logfile,
                show_on_tab=settings.show_on_tab,
                show_on_tab_keybind=settings.show_on_tab_keybind,
                check_for_updates=settings.check_for_updates,
            )
            self.display_section.set(settings.sort_order, settings.hide_dead_players)
            self.hypixel_section.set(settings.hypixel_api_key)

            self.antisniper_section.set(
                settings.use_antisniper_api, settings.antisniper_api_key
            )
            self.graphics_section.set(settings.alpha_hundredths)

    def on_close(self) -> None:
        """Reset window alpha when leaving settings page"""
        self.overlay.window.set_alpha_hundredths(
            self.controller.settings.alpha_hundredths
        )
        self.general_settings_section.show_on_tab_keybind_selector.set(False)

    def on_save(self) -> None:
        """Handle the user saving their settings"""
        # Store old value to check for rising edge
        old_check_for_updates = self.controller.settings.check_for_updates
        old_show_on_tab_keybind = self.controller.settings.show_on_tab_keybind

        (
            autodenick_teammates,
            autoselect_logfile,
            show_on_tab,
            show_on_tab_keybind,
            check_for_updates,
        ) = self.general_settings_section.get()

        sort_order, hide_dead_players = self.display_section.get(
            fallback_sort_order=self.controller.settings.sort_order
        )
        hypixel_api_key = self.hypixel_section.get()
        use_antisniper_api, antisniper_api_key = self.antisniper_section.get()

        # TODO: Add section to edit rating configs and column order
        with self.controller.settings.mutex:
            column_order = self.controller.settings.column_order
            rating_configs_dict = self.controller.settings.rating_configs.to_dict()

        known_nicks: dict[str, NickValue] = {}
        # TODO: Add section to edit known nicks
        with self.controller.settings.mutex:
            known_nicks = self.controller.settings.known_nicks.copy()

        # "Secret" settings, not editable in the GUI
        disable_overrideredirect = self.controller.settings.disable_overrideredirect
        hide_with_alpha = self.controller.settings.hide_with_alpha

        alpha_hundredths = self.graphics_section.get()

        new_settings = SettingsDict(
            hypixel_api_key=hypixel_api_key,
            antisniper_api_key=antisniper_api_key,
            use_antisniper_api=use_antisniper_api,
            sort_order=sort_order,
            column_order=column_order,
            rating_configs=rating_configs_dict,
            known_nicks=known_nicks,
            autodenick_teammates=autodenick_teammates,
            autoselect_logfile=autoselect_logfile,
            show_on_tab=show_on_tab,
            show_on_tab_keybind=show_on_tab_keybind.to_dict(),
            check_for_updates=check_for_updates,
            hide_dead_players=hide_dead_players,
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
            self.overlay.setup_tab_listener(
                restart=show_on_tab_keybind != old_show_on_tab_keybind
            )
        else:
            self.overlay.stop_tab_listener()

        # Check for updates on the rising edge of settings.check_for_updates, but
        # only if we don't already know that there is an update available
        if (
            self.controller.settings.check_for_updates
            and not old_check_for_updates
            and not self.overlay.update_available_event.is_set()
        ):
            UpdateCheckerOneShotThread(self.overlay.update_available_event).start()

        # Go back to the main content
        self.overlay.switch_page("main")
