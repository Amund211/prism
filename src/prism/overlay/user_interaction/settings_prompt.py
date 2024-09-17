import gc
import logging
import sys
import tkinter as tk
from collections.abc import Callable, Mapping

from prism.overlay.keybinds import AlphanumericKey, Key
from prism.overlay.output.overlay.gui_components import KeybindSelector, ToggleButton
from prism.overlay.settings import Settings

logger = logging.getLogger(__name__)


class ConfirmSettingsPrompt:  # pragma: nocover
    """Prompt the user to confirm their settings on initial launch"""

    def __init__(self, settings: Settings) -> None:
        # Create a root window
        self.root = tk.Tk()
        self.root.title("Confirm your settings")

        tk.Label(
            self.root,
            text="Welcome to Prism Overlay!",
            fg="green",
            font=("Consolas", 20),
        ).pack()

        tk.Label(
            self.root,
            text=(
                "Please confirm your settings below.\nYou can change these at any time"
                " in the settings menu"
            ),
            font=("Consolas", 14),
        ).pack()

        label = tk.Label(
            self.root,
            text="AutoWho",
            font=("Consolas", 14),
        )
        label.pack(side=tk.TOP, pady=(5, 0))

        subtitle_label = tk.Label(
            self.root,
            text="Automatically type /who at the start of the game",
            font=("Consolas", 10),
        )
        subtitle_label.pack(side=tk.TOP, pady=(0, 5))

        frame = tk.Frame(self.root)
        frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(3, weight=1)

        def set_interactivity(enabled: bool) -> None:
            self.chat_keybind_selector.button.config(
                state=tk.NORMAL if enabled else tk.DISABLED,
                cursor="hand2" if enabled else "arrow",
            )

        autowho_label = tk.Label(
            frame,
            text="Enable AutoWho: ",
            font=("Consolas", 12),
        )
        autowho_label.grid(row=0, column=1, sticky=tk.E)
        self.autowho_toggle = ToggleButton(frame, toggle_callback=set_interactivity)
        self.autowho_toggle.button.grid(row=0, column=2)

        chat_hotkey_label = tk.Label(
            frame,
            text="Chat hotkey: ",
            font=("Consolas", 12),
        )
        chat_hotkey_label.grid(row=1, column=1, sticky=tk.E)

        self.chat_keybind_selector = KeybindSelector(frame)
        self.chat_keybind_selector.set_key(settings.chat_hotkey)
        self.chat_keybind_selector.button.grid(row=1, column=2)

        confirm_button = tk.Button(
            self.root,
            text="Confirm",
            command=self.confirm,
            font=("Consolas", 18),
            state=tk.NORMAL,
        )
        confirm_button.pack()

        # Window close
        # sys.exit() if the user quits the window so we don't submit an invalid key
        self.root.protocol("WM_DELETE_WINDOW", sys.exit)

        self.root.update_idletasks()

    def confirm(self) -> None:
        # Destroy the window to quit the mainloop
        self.autowho = self.autowho_toggle.enabled
        self.chat_hotkey = self.chat_keybind_selector.key
        logger.info(f"User confirmed settings {self.autowho=}, {self.chat_hotkey=}")
        self.chat_keybind_selector.set(False)
        self.root.destroy()

    def run(self) -> tuple[bool, Key]:
        """Enter mainloop and return new key"""
        self.root.mainloop()

        return self.autowho, self.chat_hotkey


def confirm_settings_prompt(settings: Settings) -> tuple[bool, Key]:  # pragma: nocover
    if sys.platform == "darwin":
        return False, AlphanumericKey(name="t", char="t")
    autowho, chat_hotkey = ConfirmSettingsPrompt(settings).run()

    # Run garbage collection to clean up all the tkinter objects
    # This prevent an issue where some objects are collected later, leading to a crash
    # https://github.com/python/cpython/issues/83274
    # https://github.com/robotframework/robotframework/issues/4993#issuecomment-1908874616  # noqa: E501
    gc.collect()

    return autowho, chat_hotkey


def prompt_if_no_autowho(
    settings: Settings,
    initial_settings: Mapping[str, object],
    prompt: Callable[[Settings], tuple[bool, "Key"]] = confirm_settings_prompt,
) -> tuple[Settings, bool]:
    missing = object()
    if initial_settings.get("autowho", missing) is not missing:
        return settings, False

    logger.info("No autowho setting found in settings, prompting user to confirm")
    autowho, chat_hotkey = prompt(settings)

    new_autowho = settings.autowho != autowho
    new_hotkey = settings.chat_hotkey != chat_hotkey

    settings.autowho = autowho
    settings.chat_hotkey = chat_hotkey

    return settings, new_autowho or new_hotkey
