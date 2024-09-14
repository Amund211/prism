import functools
import logging
import string
import sys
import tkinter as tk
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from prism.overlay.behaviour import update_settings
from prism.overlay.controller import OverlayController
from prism.overlay.keybinds import Key
from prism.overlay.output.cells import (
    ALL_COLUMN_NAMES_ORDERED,
    DEFAULT_COLUMN_ORDER,
    ColumnName,
    str_is_column_name,
)
from prism.overlay.output.config import (
    DEFAULT_BBLR_CONFIG,
    DEFAULT_BEDS_CONFIG,
    DEFAULT_FINALS_CONFIG,
    DEFAULT_FKDR_CONFIG,
    DEFAULT_INDEX_CONFIG,
    DEFAULT_KDR_CONFIG,
    DEFAULT_KILLS_CONFIG,
    DEFAULT_SESSIONTIME_CONFIG,
    DEFAULT_STARS_CONFIG,
    DEFAULT_WINS_CONFIG,
    DEFAULT_WINSTREAK_CONFIG,
    DEFAULT_WLR_CONFIG,
    RatingConfig,
    RatingConfigCollection,
)
from prism.overlay.output.overlay.gui_components import (
    KeybindSelector,
    OrderedMultiSelect,
    ScrollableFrame,
    ToggleButton,
)
from prism.overlay.output.overlay.utils import open_url
from prism.overlay.settings import NickValue, Settings, SettingsDict
from prism.overlay.thread_count import recommend_stats_thread_count
from prism.overlay.threading import UpdateCheckerThread

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: nocover
    from prism.overlay.output.overlay.stats_overlay import StatsOverlay


class SupportSection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section("Support and Feedback")

        discord_button = tk.Button(
            self.frame,
            text="Join the Discord!",
            font=("Consolas", 14),
            foreground="white",
            background="#5865F2",
            command=functools.partial(open_url, "https://discord.gg/k4FGUnEHYg"),
            relief="flat",
            cursor="hand2",
        )
        discord_button.pack(side=tk.TOP)
        parent.make_widgets_scrollable(discord_button)


class AntisniperSection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section("AntiSniper API")
        self.frame.columnconfigure(0, weight=0)

        info_label = tk.Label(
            self.frame,
            text=(
                "Visit antisniper.net, join (and STAY in) the discord server and "
                "follow the instructions on how to verify to get an API key."
            ),
            font=("Consolas", 10),
            foreground="white",
            background="black",
        )
        info_label.bind("<Configure>", lambda e: info_label.config(wraplength=400))
        info_label.grid(row=0, columnspan=2)
        parent.make_widgets_scrollable(info_label)

        def set_interactivity(enabled: bool) -> None:
            self.antisniper_api_key_entry.config(
                state=tk.NORMAL if enabled else tk.DISABLED
            )

        use_antisniper_label = tk.Label(
            self.frame,
            text="AntiSniper WS estimates: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        use_antisniper_label.grid(row=1, column=0, sticky=tk.E)

        self.use_antisniper_api_toggle = ToggleButton(
            self.frame, toggle_callback=set_interactivity
        )
        self.use_antisniper_api_toggle.button.grid(row=1, column=1)
        parent.make_widgets_scrollable(
            use_antisniper_label, self.use_antisniper_api_toggle.button
        )

        api_key_label = tk.Label(
            self.frame,
            text="API key: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        api_key_label.grid(row=2, column=0, sticky=tk.E)

        self.antisniper_api_key_variable = tk.StringVar()
        self.antisniper_api_key_entry = tk.Entry(
            self.frame, show="*", textvariable=self.antisniper_api_key_variable
        )

        self.antisniper_api_key_entry.grid(row=2, column=1, sticky=tk.W + tk.E)
        self.frame.columnconfigure(1, weight=1)

        show_button = tk.Button(
            self.frame,
            text="SHOW",
            font=("Consolas", 10),
            foreground="black",
            background="gray",
            activebackground="red",
            command=lambda: self.antisniper_api_key_entry.config(show=""),
            relief="flat",
            cursor="hand2",
        )
        show_button.grid(row=2, column=2, padx=(5, 0))

        parent.make_widgets_scrollable(
            api_key_label, self.antisniper_api_key_entry, show_button
        )

    def set(self, use_antisniper_api: bool, antisniper_api_key: str | None) -> None:
        """Set the state of this section"""
        self.use_antisniper_api_toggle.set(use_antisniper_api)
        self.antisniper_api_key_entry.config(show="*")
        self.antisniper_api_key_variable.set(antisniper_api_key or "")

    def get(self) -> tuple[bool, str | None]:
        """Get the state of this section"""
        value = self.antisniper_api_key_variable.get()
        if ":" in value:
            # Handle `Apikey: 12345678-1234-1234-1234-abcdefabcdef`
            value = value[value.index(":") + 1 :]

        value = value.strip()

        key = value if len(value) > 3 else None

        return self.use_antisniper_api_toggle.enabled, key


class GeneralSettingSection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section("General Settings")
        self.frame.columnconfigure(0, weight=0)

        autodenick_label = tk.Label(
            self.frame,
            text="Autodenick teammates: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        autodenick_label.grid(row=0, column=0, sticky=tk.E)
        self.autodenick_teammates_toggle = ToggleButton(self.frame)
        self.autodenick_teammates_toggle.button.grid(row=0, column=1)
        parent.make_widgets_scrollable(
            autodenick_label,
            self.autodenick_teammates_toggle.button,
        )

        autoselect_label = tk.Label(
            self.frame,
            text="Autoselect logfile: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        autoselect_label.grid(row=1, column=0, sticky=tk.E)
        self.autoselect_logfile_toggle = ToggleButton(self.frame)
        self.autoselect_logfile_toggle.button.grid(row=1, column=1)
        parent.make_widgets_scrollable(
            autoselect_label,
            self.autoselect_logfile_toggle.button,
        )

        def disable_keybind_selector(enabled: bool) -> None:
            self.show_on_tab_keybind_selector.button.config(  # type: ignore [has-type]
                state=tk.NORMAL if enabled else tk.DISABLED,
                cursor="hand2" if enabled else "arrow",
            )

        show_on_tab_label = tk.Label(
            self.frame,
            text="Show overlay on tab: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        show_on_tab_label.grid(row=2, column=0, sticky=tk.E)
        self.show_on_tab_toggle = ToggleButton(
            self.frame, toggle_callback=disable_keybind_selector
        )
        self.show_on_tab_toggle.button.grid(row=2, column=1)
        parent.make_widgets_scrollable(
            show_on_tab_label,
            self.show_on_tab_toggle.button,
        )

        show_on_tab_hotkey_label = tk.Label(
            self.frame,
            text="Show on tab hotkey: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        show_on_tab_hotkey_label.grid(row=3, column=0, sticky=tk.E)
        self.show_on_tab_keybind_selector = KeybindSelector(
            self.frame, overlay=parent.overlay
        )
        self.show_on_tab_keybind_selector.button.grid(row=3, column=1)
        parent.make_widgets_scrollable(
            show_on_tab_hotkey_label,
            self.show_on_tab_keybind_selector.button,
        )

        def disable_include_patch_updates_toggle(enabled: bool) -> None:
            self.include_patch_updates_toggle.button.config(
                state=tk.NORMAL if enabled else tk.DISABLED,
                cursor="hand2" if enabled else "arrow",
            )

        check_for_updates_label = tk.Label(
            self.frame,
            text="Check for major version updates: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        check_for_updates_label.grid(row=4, column=0, sticky=tk.E)
        self.check_for_updates_toggle = ToggleButton(
            self.frame, toggle_callback=disable_include_patch_updates_toggle
        )
        self.check_for_updates_toggle.button.grid(row=4, column=1)
        parent.make_widgets_scrollable(
            check_for_updates_label,
            self.check_for_updates_toggle.button,
        )

        include_patch_updates_label = tk.Label(
            self.frame,
            text="Check for minor version updates: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        include_patch_updates_label.grid(row=5, column=0, sticky=tk.E)
        self.include_patch_updates_toggle = ToggleButton(self.frame)
        self.include_patch_updates_toggle.button.grid(row=5, column=1)
        parent.make_widgets_scrollable(
            include_patch_updates_label,
            self.include_patch_updates_toggle.button,
        )

        use_included_certs_label = tk.Label(
            self.frame,
            text="Use included ssl certificates:\n*Requires restart*",
            font=("Consolas", 10),
            foreground="white",
            background="black",
        )
        use_included_certs_label.grid(row=6, column=0, sticky=tk.E)
        self.use_included_certs_toggle = ToggleButton(self.frame)
        self.use_included_certs_toggle.button.grid(row=6, column=1)
        parent.make_widgets_scrollable(
            use_included_certs_label,
            self.use_included_certs_toggle.button,
        )

        if sys.platform == "darwin":
            self.show_on_tab_toggle.button.config(state=tk.DISABLED, cursor="arrow")
            self.show_on_tab_keybind_selector.button.config(
                state=tk.DISABLED, cursor="arrow"
            )

            show_on_tab_disabled_label = tk.Label(
                self.frame,
                text="SHOW ON TAB IS NOT AVAILABLE ON MAC",
                font=("Consolas", 12),
                foreground="red",
                background="black",
            )
            show_on_tab_disabled_label.grid(row=7, column=0, columnspan=2)
            parent.make_widgets_scrollable(show_on_tab_disabled_label)

    def set(
        self,
        autodenick_teammates: bool,
        autoselect_logfile: bool,
        show_on_tab: bool,
        show_on_tab_keybind: Key,
        check_for_updates: bool,
        include_patch_updates: bool,
        use_included_certs: bool,
    ) -> None:
        """Set the state of this section"""
        self.autodenick_teammates_toggle.set(autodenick_teammates)
        self.autoselect_logfile_toggle.set(autoselect_logfile)
        self.show_on_tab_toggle.set(show_on_tab)
        self.show_on_tab_keybind_selector.set_key(show_on_tab_keybind)
        self.check_for_updates_toggle.set(check_for_updates)
        self.include_patch_updates_toggle.set(include_patch_updates)
        self.use_included_certs_toggle.set(use_included_certs)

    def get(self) -> tuple[bool, bool, bool, Key, bool, bool, bool]:
        """Get the state of this section"""
        return (
            self.autodenick_teammates_toggle.enabled,
            self.autoselect_logfile_toggle.enabled,
            self.show_on_tab_toggle.enabled,
            self.show_on_tab_keybind_selector.key,
            self.check_for_updates_toggle.enabled,
            self.include_patch_updates_toggle.enabled,
            self.use_included_certs_toggle.enabled,
        )


class _DiscordSettings(TypedDict):
    discord_rich_presence: bool
    discord_show_username: bool
    discord_show_session_stats: bool
    discord_show_party: bool


class DiscordSection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section("Discord Settings")
        self.frame.columnconfigure(0, weight=0)

        info_label = tk.Label(
            self.frame,
            text=(
                "Go to Discord settings -> Activity Privacy and enable "
                "Display current activity as a status message. Make sure to start the "
                "overlay before any other application that sets your status "
                "(like Lunar client)."
            ),
            font=("Consolas", 10),
            foreground="white",
            background="black",
        )
        info_label.bind("<Configure>", lambda e: info_label.config(wraplength=400))
        info_label.grid(row=0, columnspan=2)
        parent.make_widgets_scrollable(info_label)

        discord_rich_presence_label = tk.Label(
            self.frame,
            text="Set discord activity: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        discord_rich_presence_label.grid(row=1, column=0, sticky=tk.E)
        self.discord_rich_presence_toggle = ToggleButton(
            self.frame, toggle_callback=self._enable_buttons
        )
        self.discord_rich_presence_toggle.button.grid(row=1, column=1)
        parent.make_widgets_scrollable(
            discord_rich_presence_label,
            self.discord_rich_presence_toggle.button,
        )

        discord_show_username_label = tk.Label(
            self.frame,
            text="Show username: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        discord_show_username_label.grid(row=2, column=0, sticky=tk.E)
        self.discord_show_username_toggle = ToggleButton(self.frame)
        self.discord_show_username_toggle.button.grid(row=2, column=1)
        parent.make_widgets_scrollable(
            discord_show_username_label,
            self.discord_show_username_toggle.button,
        )

        discord_show_session_stats_label = tk.Label(
            self.frame,
            text="Show session stats: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        discord_show_session_stats_label.grid(row=3, column=0, sticky=tk.E)
        self.discord_show_session_stats_toggle = ToggleButton(self.frame)
        self.discord_show_session_stats_toggle.button.grid(row=3, column=1)
        parent.make_widgets_scrollable(
            discord_show_session_stats_label,
            self.discord_show_session_stats_toggle.button,
        )

        discord_show_party_label = tk.Label(
            self.frame,
            text="Show party: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        discord_show_party_label.grid(row=4, column=0, sticky=tk.E)
        self.discord_show_party_toggle = ToggleButton(self.frame)
        self.discord_show_party_toggle.button.grid(row=4, column=1)
        parent.make_widgets_scrollable(
            discord_show_party_label,
            self.discord_show_party_toggle.button,
        )

    def _enable_buttons(self, enabled: bool) -> None:
        """Set the state of the settings buttons to `enabled`"""
        state: Literal["normal", "disabled"] = tk.NORMAL if enabled else tk.DISABLED
        cursor: Literal["hand2", "arrow"] = "hand2" if enabled else "arrow"
        self.discord_show_username_toggle.button.config(state=state, cursor=cursor)
        self.discord_show_session_stats_toggle.button.config(state=state, cursor=cursor)
        self.discord_show_party_toggle.button.config(state=state, cursor=cursor)

    def set(
        self,
        discord_rich_presence: bool,
        discord_show_username: bool,
        discord_show_session_stats: bool,
        discord_show_party: bool,
    ) -> None:
        """Set the state of this section"""
        self.discord_rich_presence_toggle.set(discord_rich_presence)
        self.discord_show_username_toggle.set(discord_show_username)
        self.discord_show_session_stats_toggle.set(discord_show_session_stats)
        self.discord_show_party_toggle.set(discord_show_party)

    def get(self) -> _DiscordSettings:
        """Get the state of this section"""
        return {
            "discord_rich_presence": self.discord_rich_presence_toggle.enabled,
            "discord_show_username": self.discord_show_username_toggle.enabled,
            "discord_show_session_stats": self.discord_show_session_stats_toggle.enabled,  # noqa: E501
            "discord_show_party": self.discord_show_party_toggle.enabled,
        }


class PerformanceSection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section("Performance Settings")
        self.frame.columnconfigure(0, weight=0)

        stats_thread_explanation_label = tk.Label(
            self.frame,
            text=(
                "How many players the overlay tries to download stats for at the same "
                "time. Try decreasing this if the overlay is lagging. REQUIRES RESTART!"
            ),
            font=("Consolas", 10),
            foreground="white",
            background="black",
        )
        stats_thread_explanation_label.bind(
            "<Configure>",
            lambda e: stats_thread_explanation_label.config(wraplength=400),
        )
        stats_thread_explanation_label.grid(row=5, column=0, columnspan=3)

        stats_thread_count_label = tk.Label(
            self.frame,
            text="Stats threads: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        stats_thread_count_label.grid(row=6, column=0, sticky=tk.E)

        self.stats_thread_count_variable = tk.IntVar(value=2)
        stats_thread_count_scale = tk.Scale(
            self.frame,
            from_=1,
            to=16,
            orient=tk.HORIZONTAL,
            length=200,
            foreground="white",
            background="black",
            variable=self.stats_thread_count_variable,
        )
        stats_thread_count_scale.grid(row=6, column=1)

        reset_button = tk.Button(
            self.frame,
            text="Reset",
            font=("Consolas", 14),
            foreground="white",
            background="black",
            command=functools.partial(
                self.stats_thread_count_variable.set, recommend_stats_thread_count()
            ),
            relief="flat",
            cursor="hand2",
        )
        reset_button.grid(row=6, column=2)

        parent.make_widgets_scrollable(
            stats_thread_explanation_label,
            stats_thread_count_label,
            stats_thread_count_scale,
            reset_button,
        )

    def clamp_stats_thread_count(self, stats_thread_count: int) -> int:
        """Clamp the stats_thread_count to a valid range"""
        return min(16, max(1, stats_thread_count))

    def set(self, stats_thread_count: int) -> None:
        """Set the state of this section"""
        self.stats_thread_count_variable.set(
            self.clamp_stats_thread_count(stats_thread_count)
        )

    def get(self) -> int:
        """Get the state of this section"""
        return self.clamp_stats_thread_count(self.stats_thread_count_variable.get())


class DisplaySection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section(
            "Display Settings", "Customize the stats table display"
        )
        self.frame.columnconfigure(0, weight=0)

        sort_order_label = tk.Label(
            self.frame,
            text="Sort order: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        sort_order_label.grid(row=0, column=0, sticky=tk.E)

        self.sort_order_variable = tk.StringVar(value="")
        self.sort_order_menu = tk.OptionMenu(
            self.frame, self.sort_order_variable, *ALL_COLUMN_NAMES_ORDERED
        )
        self.sort_order_menu.grid(row=0, column=1)
        parent.make_widgets_scrollable(sort_order_label, self.sort_order_menu)

        hide_dead_players_label = tk.Label(
            self.frame,
            text="Hide dead players: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        hide_dead_players_label.grid(row=1, column=0, sticky=tk.E)
        self.hide_dead_players_toggle = ToggleButton(self.frame)
        self.hide_dead_players_toggle.button.grid(row=1, column=1)
        parent.make_widgets_scrollable(
            hide_dead_players_label, self.hide_dead_players_toggle.button
        )

        autohide_timeout_label = tk.Label(
            self.frame,
            text="Autohide timeout (s): ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        autohide_timeout_label.grid(row=6, column=0, sticky=tk.E)

        self.autohide_timeout_variable = tk.IntVar(value=8)
        autohide_timeout_scale = tk.Scale(
            self.frame,
            from_=1,
            to=20,
            orient=tk.HORIZONTAL,
            length=200,
            foreground="white",
            background="black",
            variable=self.autohide_timeout_variable,
        )
        autohide_timeout_scale.grid(row=6, column=1)

        reset_autohide_timeout_button = tk.Button(
            self.frame,
            text="Reset",
            font=("Consolas", 14),
            foreground="white",
            background="black",
            command=functools.partial(self.autohide_timeout_variable.set, 8),
            relief="flat",
            cursor="hand2",
        )
        reset_autohide_timeout_button.grid(row=6, column=2)

        parent.make_widgets_scrollable(
            autohide_timeout_label,
            autohide_timeout_scale,
            reset_autohide_timeout_button,
        )

    def clamp_autohide_timeout(self, autohide_timeout: int) -> int:
        """Clamp the autohide_timeout to a valid range"""
        return min(20, max(1, autohide_timeout))

    def set(
        self, sort_order: ColumnName, hide_dead_players: bool, autohide_timeout: int
    ) -> None:
        """Set the state of this section"""
        self.sort_order_variable.set(sort_order)
        self.hide_dead_players_toggle.set(hide_dead_players)
        self.autohide_timeout_variable.set(autohide_timeout)

    def get(self, fallback_sort_order: ColumnName) -> tuple[ColumnName, bool, int]:
        """Get the state of this section"""
        sort_order: str | ColumnName = self.sort_order_variable.get()

        if not str_is_column_name(sort_order):
            logger.error(
                f"Tried saving invalid sort order {sort_order} "
                f"Falling back to {fallback_sort_order}."
            )
            sort_order = fallback_sort_order

        return (
            sort_order,
            self.hide_dead_players_toggle.enabled,
            self.clamp_autohide_timeout(self.autohide_timeout_variable.get()),
        )


class ColumnSection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.frame = parent.make_section(
            "Column Settings", "Select which columns to show and their order"
        )

        self.column_order_selection = OrderedMultiSelect(
            self.frame, ALL_COLUMN_NAMES_ORDERED, reset_items=DEFAULT_COLUMN_ORDER
        )
        self.column_order_selection.frame.pack(side=tk.TOP, fill=tk.BOTH)

        parent.make_widgets_scrollable(
            self.column_order_selection.frame,
            self.column_order_selection.listbox,
            self.column_order_selection.toggle_frame,
            *(toggle.button for toggle in self.column_order_selection.toggles.values()),
            self.column_order_selection.reset_button,
        )

    def set(self, column_order: tuple[ColumnName, ...]) -> None:
        """Set the state of this section"""
        self.column_order_selection.set_selection(column_order)
        pass

    def get(self) -> tuple[ColumnName, ...]:
        """Get the state of this section"""
        selection = self.column_order_selection.get_selection()

        if not all(str_is_column_name(column) for column in selection):
            logger.error(f"Got non-column names from selection {selection}!")

        column_order = tuple(filter(str_is_column_name, selection))

        if not column_order:
            column_order = DEFAULT_COLUMN_ORDER

        return column_order


class GraphicsSection:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.parent = parent
        self.frame = parent.make_section("Graphics")
        self.frame.columnconfigure(0, weight=0)

        self.alpha_hundredths_variable = tk.IntVar(value=80)
        self.alpha_hundredths_variable.trace_add("write", self.set_window_alpha)
        alpha_label = tk.Label(
            self.frame,
            text="Alpha: ",
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        alpha_label.grid(row=0, column=0, sticky=tk.E)

        alpha_scale = tk.Scale(
            self.frame,
            from_=10,
            to=100,
            orient=tk.HORIZONTAL,
            length=200,
            foreground="white",
            background="black",
            variable=self.alpha_hundredths_variable,
        )
        alpha_scale.grid(row=0, column=1)

        parent.make_widgets_scrollable(alpha_label, alpha_scale)

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


class RatingConfigEditor:  # pragma: nocover
    """Component to edit one rating config"""

    def __init__(
        self, parent: "StatsSetting", name: str, default: RatingConfig
    ) -> None:
        self.frame = parent.make_rating_config_section()
        self.default = default

        name_label = tk.Label(
            self.frame,
            text=name,
            font=("Consolas", 12),
            foreground="white",
            background="black",
        )
        name_label.pack(side=tk.TOP, pady=(5, 0))

        first_frame = tk.Frame(self.frame, background="black")
        first_frame.pack(side=tk.TOP, fill=tk.X, pady=(5, 0))
        for i in range(4):
            first_frame.columnconfigure(i, weight=1)

        levels_frame = tk.Frame(self.frame, background="black")
        levels_frame.pack(side=tk.TOP, fill=tk.X, pady=(5, 5))
        for i in range(5):
            levels_frame.columnconfigure(i, weight=1)

        reset_button = tk.Button(
            self.frame,
            text="Reset",
            font=("Consolas", 14),
            foreground="white",
            background="black",
            command=functools.partial(self.set, default),
            relief="flat",
            cursor="hand2",
        )
        reset_button.pack(side=tk.TOP, pady=(0, 5))

        parent.parent.make_widgets_scrollable(
            name_label, first_frame, levels_frame, reset_button
        )

        color_by_level_label = tk.Label(
            first_frame,
            text="Color by level: ",
            font=("Consolas", 10),
            foreground="white",
            background="black",
        )
        color_by_level_label.grid(row=0, column=0, sticky=tk.E)

        self.rate_by_level_toggle = ToggleButton(
            first_frame, toggle_callback=lambda enabled: self._set_component_state()
        )
        self.rate_by_level_toggle.button.grid(row=0, column=1, sticky=tk.W)
        parent.parent.make_widgets_scrollable(
            color_by_level_label, self.rate_by_level_toggle.button
        )

        decimals_label = tk.Label(
            first_frame,
            text="Decimals: ",
            font=("Consolas", 10),
            foreground="white",
            background="black",
        )
        decimals_label.grid(row=0, column=2, sticky=tk.E)

        self.decimals_spinbox = tk.Spinbox(first_frame, from_=0, to=6, width=2)
        self.decimals_spinbox.grid(row=0, column=3, sticky=tk.W)
        parent.parent.make_widgets_scrollable(decimals_label, self.decimals_spinbox)

        sort_ascending_label = tk.Label(
            first_frame,
            text="Sort order:",
            font=("Consolas", 10),
            foreground="white",
            background="black",
        )
        sort_ascending_label.grid(row=1, column=0, sticky=tk.E)

        self.sort_descending_toggle = ToggleButton(
            first_frame,
            toggle_callback=lambda enabled: self._set_component_state(flip_levels=True),
            enabled_config={"text": "Descending"},
            disabled_config={
                "text": "Ascending ",
                "background": "dodger blue",
                "activebackground": "deep sky blue",
            },
        )
        self.sort_descending_toggle.button.grid(row=1, column=1, sticky=tk.W)
        parent.parent.make_widgets_scrollable(
            sort_ascending_label, self.sort_descending_toggle.button
        )

        levels_label = tk.Label(
            levels_frame,
            text="Levels:",
            font=("Consolas", 10),
            foreground="white",
            background="black",
        )
        levels_label.grid(row=2, column=0, columnspan=1)
        parent.parent.make_widgets_scrollable(levels_label)

        self.level_entry_variables = [tk.StringVar() for i in range(4)]
        self.level_entries = [
            tk.Entry(levels_frame, textvariable=level_entry_variable, width=10)
            for i, level_entry_variable in enumerate(self.level_entry_variables)
        ]
        self.less_than_or_greater_than_labels: list[tk.Label] = []
        for i, (classification, level_entry) in enumerate(
            zip(("Meh", "Decent", "Good", "Scary"), self.level_entries, strict=True)
        ):
            classification_label = tk.Label(
                levels_frame,
                text=classification,
                font=("Consolas", 10),
                foreground="white",
                background="black",
            )
            classification_label.grid(row=1, column=2 * i + 1)
            parent.parent.make_widgets_scrollable(classification_label)

            level_entry.grid(row=2, column=2 * i + 1)

            if i <= 2:
                less_than_or_greater_than_label = tk.Label(
                    levels_frame,
                    text="≤",
                    font=("Consolas", 10),
                    foreground="white",
                    background="black",
                )
                less_than_or_greater_than_label.grid(row=2, column=2 * (i + 1))
                self.less_than_or_greater_than_labels.append(
                    less_than_or_greater_than_label
                )
                parent.parent.make_widgets_scrollable(less_than_or_greater_than_label)

        parent.parent.make_widgets_scrollable(levels_label, *self.level_entries)

    def _set_component_state(self, flip_levels: bool = False) -> None:
        """Disable level entries when not rating by level"""
        state = self.get()
        # Disable level entries when not rating by level
        for level_entry in self.level_entries:
            level_entry.config(state=tk.NORMAL if state.rate_by_level else tk.DISABLED)

        # Display the order the levels should be in depending on sort order
        for less_than_or_greater_than_label in self.less_than_or_greater_than_labels:
            less_than_or_greater_than_label.config(
                text="≥" if state.sort_ascending else "≤"
            )

        if flip_levels:
            # Flip the levels when changing sort order
            old_levels = [level_entry.get() for level_entry in self.level_entries]
            for new_level, level_entry_variable in zip(
                reversed(old_levels), self.level_entry_variables
            ):
                level_entry_variable.set(new_level)

    def set(self, rating_config: RatingConfig) -> None:
        """Set the state of this section"""
        self.rate_by_level_toggle.set(
            rating_config.rate_by_level, disable_toggle_callback=True
        )
        self.decimals_spinbox.delete(0)
        self.decimals_spinbox.insert(0, str(rating_config.decimals))
        self.sort_descending_toggle.set(
            not rating_config.sort_ascending, disable_toggle_callback=True
        )
        for level_value, level_entry_variable in zip(
            rating_config.levels, self.level_entry_variables
        ):
            level_entry_variable.set(f"{level_value:.1f}")

        if len(rating_config.levels) != 4:
            logger.warning(
                f"Levels with non-standard length set, {rating_config.levels}"
            )

        self._set_component_state()

    def _get_levels(self) -> tuple[float, ...]:
        """Get the levels from the entries. Fallback to the default."""
        valid_characters = frozenset(string.digits + ".")

        levels: list[float] = []
        for level_entry_variable, default_level in zip(
            self.level_entry_variables, self.default.levels, strict=True
        ):
            value = level_entry_variable.get()
            clean_value = "".join(
                filter(
                    lambda char: char in valid_characters,
                    value.strip().replace(",", "."),
                )
            )
            try:
                float_value = float(clean_value)
            except ValueError:
                logger.info(
                    f"Failed parsing float from {value}. "
                    f"Falling back to {default_level}."
                )
                float_value = default_level

            levels.append(float_value)

        return tuple(levels)

    def get(self) -> RatingConfig:
        """Get the state of this section"""
        raw_decimals = self.decimals_spinbox.get()
        try:
            decimals = int(raw_decimals)
        except ValueError:
            logger.exception(
                f"Failed parsing int from {raw_decimals}. "
                f"Falling back to {self.default.decimals}."
            )
            decimals = self.default.decimals

        return RatingConfig(
            self.rate_by_level_toggle.enabled,
            self._get_levels(),
            decimals,
            not self.sort_descending_toggle.enabled,
        )


class StatsSetting:  # pragma: nocover
    def __init__(self, parent: "SettingsPage") -> None:
        self.parent = parent
        self.frame = parent.make_section("Stats Settings")
        self.frame.columnconfigure(0, weight=0)

        self.sessiontime_editor = RatingConfigEditor(
            self, "sessiontime", DEFAULT_SESSIONTIME_CONFIG
        )
        self.stars_editor = RatingConfigEditor(self, "stars", DEFAULT_STARS_CONFIG)
        self.index_editor = RatingConfigEditor(self, "index", DEFAULT_INDEX_CONFIG)
        self.fkdr_editor = RatingConfigEditor(self, "fkdr", DEFAULT_FKDR_CONFIG)
        self.kdr_editor = RatingConfigEditor(self, "kdr", DEFAULT_KDR_CONFIG)
        self.bblr_editor = RatingConfigEditor(self, "bblr", DEFAULT_BBLR_CONFIG)
        self.wlr_editor = RatingConfigEditor(self, "wlr", DEFAULT_WLR_CONFIG)
        self.winstreak_editor = RatingConfigEditor(
            self, "winstreak", DEFAULT_WINSTREAK_CONFIG
        )
        self.kills_editor = RatingConfigEditor(self, "kills", DEFAULT_KILLS_CONFIG)
        self.finals_editor = RatingConfigEditor(self, "finals", DEFAULT_FINALS_CONFIG)
        self.beds_editor = RatingConfigEditor(self, "beds", DEFAULT_BEDS_CONFIG)
        self.wins_editor = RatingConfigEditor(self, "wins", DEFAULT_WINS_CONFIG)

    def make_rating_config_section(self) -> tk.Frame:
        config_section_frame = tk.Frame(
            self.frame, background="black", highlightthickness=1
        )
        config_section_frame.pack(side=tk.TOP, fill=tk.X, pady=(5, 0))
        self.parent.make_widgets_scrollable(config_section_frame)

        return config_section_frame

    def set(self, rating_configs: RatingConfigCollection) -> None:
        """Set the state of this section"""
        self.sessiontime_editor.set(rating_configs.sessiontime)
        self.stars_editor.set(rating_configs.stars)
        self.index_editor.set(rating_configs.index)
        self.fkdr_editor.set(rating_configs.fkdr)
        self.kdr_editor.set(rating_configs.kdr)
        self.bblr_editor.set(rating_configs.bblr)
        self.wlr_editor.set(rating_configs.wlr)
        self.winstreak_editor.set(rating_configs.winstreak)
        self.kills_editor.set(rating_configs.kills)
        self.finals_editor.set(rating_configs.finals)
        self.beds_editor.set(rating_configs.beds)
        self.wins_editor.set(rating_configs.wins)

    def get(self) -> RatingConfigCollection:
        """Get the state of this section"""
        return RatingConfigCollection(
            stars=self.stars_editor.get(),
            index=self.index_editor.get(),
            fkdr=self.fkdr_editor.get(),
            kdr=self.kdr_editor.get(),
            bblr=self.bblr_editor.get(),
            wlr=self.wlr_editor.get(),
            winstreak=self.winstreak_editor.get(),
            kills=self.kills_editor.get(),
            finals=self.finals_editor.get(),
            beds=self.beds_editor.get(),
            wins=self.wins_editor.get(),
            sessiontime=self.sessiontime_editor.get(),
        )


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
            side=tk.BOTTOM, expand=True, fill=tk.X, padx=5, pady=(3, 0)
        )

        # Save button
        save_button = tk.Button(
            self.controls_frame,
            text="Save",
            font=("Consolas", 14),
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
            font=("Consolas", 14),
            foreground="white",
            background="black",
            command=lambda: self.overlay.switch_page("main"),
            relief="flat",
            cursor="hand2",
        )
        cancel_button.pack(side=tk.RIGHT, padx=(0, 5))

        # A frame for the settings
        settings_frame_wrapper = tk.Frame(self.frame, background="black")
        settings_frame_wrapper.pack(side=tk.TOP, fill=tk.BOTH)
        self.scrollable_settings_frame = ScrollableFrame(
            settings_frame_wrapper, max_height=600
        )
        self.scrollable_settings_frame.container_frame.pack(side=tk.TOP, fill=tk.BOTH)

        SupportSection(self)
        self.general_settings_section = GeneralSettingSection(self)
        self.display_section = DisplaySection(self)
        self.column_section = ColumnSection(self)
        self.antisniper_section = AntisniperSection(self)
        self.discord_section = DiscordSection(self)
        self.performance_section = PerformanceSection(self)
        self.graphics_section = GraphicsSection(self)
        self.stats_section = StatsSetting(self)

    def make_widgets_scrollable(self, *widgets: tk.Widget) -> None:
        """Make the given widgets scroll the settings page"""
        for widget in widgets:
            self.scrollable_settings_frame.register_scrollarea(widget)

    def make_section(
        self, section_header: str, subtitle: str | None = None
    ) -> tk.Frame:
        """Make a settings section with a header and a frame for the settings"""
        label = tk.Label(
            self.scrollable_settings_frame.content_frame,
            text=section_header,
            font=("Consolas", 14),
            foreground="white",
            background="black",
        )
        label.pack(side=tk.TOP, pady=(5, 0))
        self.make_widgets_scrollable(label)

        if subtitle is not None:
            subtitle_label = tk.Label(
                self.scrollable_settings_frame.content_frame,
                text=subtitle,
                font=("Consolas", 10),
                foreground="white",
                background="black",
            )
            subtitle_label.pack(side=tk.TOP, pady=(0, 5))
            self.make_widgets_scrollable(subtitle_label)

        section_frame = tk.Frame(
            self.scrollable_settings_frame.content_frame, background="black"
        )
        section_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0, 10))
        self.make_widgets_scrollable(section_frame)

        return section_frame

    def set_content(self, settings: Settings) -> None:
        """Set the content of the page to the values from `settings`"""
        self.scrollable_settings_frame.scroll_to_top()

        with settings.mutex:
            self.antisniper_section.set(
                use_antisniper_api=settings.use_antisniper_api,
                antisniper_api_key=settings.antisniper_api_key,
            )
            self.general_settings_section.set(
                autodenick_teammates=settings.autodenick_teammates,
                autoselect_logfile=settings.autoselect_logfile,
                show_on_tab=settings.show_on_tab,
                show_on_tab_keybind=settings.show_on_tab_keybind,
                check_for_updates=settings.check_for_updates,
                include_patch_updates=settings.include_patch_updates,
                use_included_certs=settings.use_included_certs,
            )
            self.performance_section.set(stats_thread_count=settings.stats_thread_count)
            self.display_section.set(
                settings.sort_order,
                settings.hide_dead_players,
                settings.autohide_timeout,
            )
            self.column_section.set(settings.column_order)

            self.discord_section.set(
                discord_rich_presence=settings.discord_rich_presence,
                discord_show_username=settings.discord_show_username,
                discord_show_session_stats=settings.discord_show_session_stats,
                discord_show_party=settings.discord_show_party,
            )
            self.graphics_section.set(settings.alpha_hundredths)
            self.stats_section.set(settings.rating_configs)

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
        old_include_patch_updates = self.controller.settings.include_patch_updates
        old_show_on_tab_keybind = self.controller.settings.show_on_tab_keybind

        user_id = self.controller.settings.user_id
        hypixel_api_key = self.controller.settings.hypixel_api_key

        use_antisniper_api, antisniper_api_key = self.antisniper_section.get()
        (
            autodenick_teammates,
            autoselect_logfile,
            show_on_tab,
            show_on_tab_keybind,
            check_for_updates,
            include_patch_updates,
            use_included_certs,
        ) = self.general_settings_section.get()

        stats_thread_count = self.performance_section.get()

        sort_order, hide_dead_players, autohide_timeout = self.display_section.get(
            fallback_sort_order=self.controller.settings.sort_order
        )
        column_order = self.column_section.get()

        discord_settings = self.discord_section.get()

        known_nicks: dict[str, NickValue] = {}
        # TODO: Add section to edit known nicks
        with self.controller.settings.mutex:
            known_nicks = self.controller.settings.known_nicks.copy()

        # "Secret" settings, not editable in the GUI
        disable_overrideredirect = self.controller.settings.disable_overrideredirect
        hide_with_alpha = self.controller.settings.hide_with_alpha

        alpha_hundredths = self.graphics_section.get()

        rating_configs = self.stats_section.get()

        new_settings = SettingsDict(
            user_id=user_id,
            hypixel_api_key=hypixel_api_key,
            antisniper_api_key=antisniper_api_key,
            use_antisniper_api=use_antisniper_api,
            sort_order=sort_order,
            column_order=column_order,
            rating_configs=rating_configs.to_dict(),
            known_nicks=known_nicks,
            autodenick_teammates=autodenick_teammates,
            autoselect_logfile=autoselect_logfile,
            autohide_timeout=autohide_timeout,
            show_on_tab=show_on_tab,
            show_on_tab_keybind=show_on_tab_keybind.to_dict(),
            check_for_updates=check_for_updates,
            include_patch_updates=include_patch_updates,
            use_included_certs=use_included_certs,
            stats_thread_count=stats_thread_count,
            discord_rich_presence=discord_settings["discord_rich_presence"],
            discord_show_username=discord_settings["discord_show_username"],
            discord_show_session_stats=discord_settings["discord_show_session_stats"],
            discord_show_party=discord_settings["discord_show_party"],
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

        # Check for updates if our related settings changed, but only if we have checks
        # enabled and if we don't already know that there is an update available
        if (
            (check_for_updates, include_patch_updates)
            != (old_check_for_updates, old_include_patch_updates)
            and check_for_updates
            and not self.overlay.update_available_event.is_set()
        ):
            UpdateCheckerThread(
                one_shot=True,
                update_available_event=self.overlay.update_available_event,
                controller=self.controller,
            ).start()

        # Go back to the main content
        self.overlay.switch_page("main")
