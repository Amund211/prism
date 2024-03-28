import logging
import sys
import tkinter as tk
import tkinter.filedialog
from typing import Any

from prism.overlay.output.overlay.utils import open_url
from prism.overlay.settings import api_key_is_valid

logger = logging.getLogger(__name__)


class APIKeyPrompt:  # pragma: nocover
    """Window to prompt the user to enter their antisniper api key"""

    def __init__(self) -> None:
        # Create a root window
        self.root = tk.Tk()
        self.root.title("Enter AntiSniper API key")

        tk.Label(
            self.root,
            text=(
                "This overlay requires an AntiSniper API key.\n"
                "Please follow the instructions below."
            ),
            fg="red",
            font=("Consolas", 20),
        ).pack()

        tk.Label(
            self.root,
            text=(
                "Visit antisniper.net, join (and STAY in) the discord server and \n"
                "follow the instructions on how to verify to get an API key. \n"
            ),
            font=("Consolas", 14),
        ).pack()

        tk.Button(
            self.root,
            text="Get API key",
            command=lambda: open_url("https://antisniper.net/"),
            font=("Consolas", 18),
            fg="green",
        ).pack()

        tk.Label(
            self.root,
            text=(
                "The prism overlay is not affiliated with AntiSniper, but they "
                "generously host the stats backend for this overlay.\n"
                "Additionally, the overlay uses features like winstreak estimates "
                "and denicking from the AntiSniper API.\n"
                "These can be disabled in settings."
            ),
            font=("Consolas", 8),
        ).pack()

        self.api_key_variable = tk.StringVar()
        self.api_key_variable.trace(
            "w", self.on_edit_api_key
        )  # type: ignore [no-untyped-call]
        tk.Entry(
            self.root,
            textvariable=self.api_key_variable,
            font=("Consolas", 18),
        ).pack()

        self.submit_button = tk.Button(
            self.root,
            text="Submit",
            command=self.submit,
            font=("Consolas", 18),
            state=tk.DISABLED,
        )
        self.submit_button.pack()

        # Window close
        # sys.exit() if the user quits the window so we don't submit an invalid key
        self.root.protocol("WM_DELETE_WINDOW", sys.exit)

        self.root.update_idletasks()

    def on_edit_api_key(self, *args: Any, **kwargs: Any) -> None:
        new_key = self.api_key_variable.get()
        self.submit_button.config(
            state=tk.NORMAL if api_key_is_valid(new_key) else tk.DISABLED
        )

    def submit(self) -> None:
        self.new_key = self.api_key_variable.get()
        self.root.destroy()

    def run(self) -> str:
        """Enter mainloop and return new key"""
        self.root.mainloop()

        if self.new_key is None:
            logger.error("API key prompt did not return a value - exiting")
            sys.exit()

        return self.new_key


def wait_for_api_key() -> str:  # pragma: nocover
    return APIKeyPrompt().run()
