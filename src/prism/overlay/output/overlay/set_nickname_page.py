import logging
import tkinter as tk
from typing import TYPE_CHECKING, Any

from prism.overlay.behaviour import set_nickname
from prism.overlay.controller import OverlayController

if TYPE_CHECKING:  # pragma: nocover
    from prism.overlay.output.overlay.stats_overlay import StatsOverlay
    from prism.overlay.output.overlay.utils import ColumnKey


NO_USERNAME_CHOICE = "No username (remove the entry)"
SELECT_AN_OPTION_CHOICE = "Select an option"

logger = logging.getLogger(__name__)


class SetNicknamePage:  # pragma: nocover
    """Page for manually setting nickname for players"""

    def __init__(
        self,
        parent: tk.Misc,
        overlay: "StatsOverlay[ColumnKey]",
        controller: OverlayController,
    ) -> None:
        """Set up a frame containing the gui"""
        self.frame = tk.Frame(parent, background="black")

        self.overlay = overlay
        self.controller = controller

        self.current_nickname: str | None = None

        # Frame for the save and cancel buttons
        self.controls_frame = tk.Frame(self.frame, background="black")
        self.controls_frame.pack(
            side=tk.BOTTOM, expand=True, fill=tk.X, padx=5, pady=(0, 3)
        )

        # Save button
        self.save_button = tk.Button(
            self.controls_frame,
            text="Save",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            command=self.on_save,
            relief="flat",
        )
        self.save_button.pack(side=tk.RIGHT)

        # Cancel button
        cancel_button = tk.Button(
            self.controls_frame,
            text="Cancel",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            command=lambda: self.overlay.switch_page("main"),
            relief="flat",
        )
        cancel_button.pack(side=tk.RIGHT, padx=(0, 5))

        # Title
        self.title_label = tk.Label(
            self.frame,
            text="",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
        )
        self.title_label.pack(side=tk.TOP, pady=(5, 0))

        # A frame for the input
        self.input_frame = tk.Frame(self.frame, background="black")
        self.input_frame.pack(side=tk.TOP, fill=tk.BOTH, padx=5, pady=(0, 10))

        self.username_var = tk.StringVar()

        def enable_button(*args: Any, **kwargs: Any) -> None:
            self.save_button.config(
                state="normal"
                if self.username_var.get() != SELECT_AN_OPTION_CHOICE
                else "disabled"
            )

        self.username_var.trace("w", enable_button)  # type: ignore [no-untyped-call]

        self.username_menu = tk.OptionMenu(
            self.input_frame, self.username_var, SELECT_AN_OPTION_CHOICE
        )
        self.username_menu.pack()

    def set_content(self, nickname: str) -> None:
        """Set the content of the page to match the given nick and the party members"""
        # Store a persistent view to the current state
        state = self.controller.state

        # Store what nick we are denicking
        self.current_nickname = nickname

        # Tell the user which nickname they selected
        self.title_label.config(text=f"Set username for {nickname}")

        # Clear previous choice
        self.username_var.set(SELECT_AN_OPTION_CHOICE)
        self.save_button.config(state="disabled")

        # Usernames in your party but not in the lobby
        potential_usernames = state.party_members.difference(state.lobby_players)

        # Set choices of dropdown
        self.username_menu["menu"].delete(0, "end")

        for username in potential_usernames:
            self.username_menu["menu"].add_command(
                label=username, command=tk._setit(self.username_var, username)
            )

        self.username_menu["menu"].add_command(
            label=NO_USERNAME_CHOICE,
            command=tk._setit(self.username_var, NO_USERNAME_CHOICE),
        )

    def on_save(self) -> None:
        """Handle the user saving their settings"""
        selected_username: str | None = self.username_var.get()

        if selected_username == SELECT_AN_OPTION_CHOICE:
            return

        if selected_username == NO_USERNAME_CHOICE:
            selected_username = None

        assert self.current_nickname is not None

        logger.info(
            f"Setting denick {self.current_nickname} => {selected_username} from gui"
        )

        set_nickname(
            username=selected_username,
            nick=self.current_nickname,
            controller=self.controller,
        )

        # Go back to the main content
        self.overlay.switch_page("main")
