import functools
import logging
import sys
import time
import tkinter as tk
import tkinter.filedialog
from collections.abc import Callable
from pathlib import Path
from typing import Any

import toml

from prism.overlay.user_interaction.logfile_utils import (
    file_exists,
    get_timestamp,
    suggest_logfiles,
)

logger = logging.getLogger(__name__)


class LogfilePrompt:  # pragma: nocover
    """Window to prompt the user to select a logfile"""

    # Number of seconds for a logfile to be considered recently used
    RECENT_TIMEOUT = 60

    def __init__(
        self,
        known_logfiles: tuple[str, ...],
        last_used: str | None,
        autoselect_logfile: bool,
        remove_logfile: Callable[[str], None],
        choose_logfile: Callable[[str], None],
    ):
        self.known_logfiles = known_logfiles
        self.last_used = last_used
        self.autoselect_logfile = autoselect_logfile
        self.remove_logfile = remove_logfile
        self.choose_logfile = choose_logfile

        self.logfile_recent = tuple(False for logfile in self.known_logfiles)

        self.task_id: str | None = None

        # Create a root window
        self.root = tk.Tk()
        self.root.title("Select a version")

        tk.Label(
            self.root,
            text="Select the logfile corresponding to the version you will be playing",
        ).pack()
        tk.Label(
            self.root, text="Recently used versions are highlighted in green", fg="red"
        ).pack()

        if self.autoselect_logfile and self.last_used is not None:
            tk.Label(
                self.root,
                text=(
                    "Your last used version will be "
                    "automatically selected when available"
                ),
                fg="green",
            ).pack()

        tk.Button(
            self.root, text="Select a new file", command=self.make_selection
        ).pack()

        self.logfile_list_frame = tk.Frame()
        self.logfile_list_frame.pack()
        self.selected_logfile_var = tk.StringVar(value=self.last_used)
        self.selected_logfile_var.trace(
            "w", self.update_buttonstate
        )  # type: ignore [no-untyped-call]
        self.rows: list[tuple[tk.Frame, tk.Button, tk.Label, tk.Radiobutton]] = []

        self.submit_button = tk.Button(
            self.root,
            text="Submit",
            state=tk.DISABLED if self.last_used is None else tk.NORMAL,
            command=self.submit_selection,
        )
        self.submit_button.pack()

        # sys.exit() if the user quits the window, otherwise we would get stuck at
        # *_thread.join()
        # Cancel button
        tk.Button(self.root, text="Cancel", command=sys.exit).pack()

        def on_close() -> None:
            self.cancel_polling()
            sys.exit()

        # Window close
        self.root.protocol("WM_DELETE_WINDOW", on_close)

        self.root.update_idletasks()

        self.update_logfile_order()

        self.update_logfile_list()

    def update_buttonstate(self, *args: Any, **kwargs: Any) -> None:
        self.submit_button.configure(
            state=tk.DISABLED
            if self.selected_logfile_var.get() not in self.known_logfiles
            else tk.NORMAL
        )

    def make_selection(self) -> None:
        result = tk.filedialog.askopenfilename(
            parent=self.root,
            title="Select launcher logfile",
            filetypes=(
                ("latest.log", "latest.log"),
                ("Text/log", ".txt .log"),
                ("All files", "*.*"),
            ),
        )

        # NOTE: mypy says result is a str, but if you cancel the selection it returns
        # an empty tuple for some reason. We check for this here.
        if isinstance(result, str) and len(result) > 0:
            self.submit_selection(result)

    def remove_logfile_and_update(self, logfile: str) -> None:
        """Remove the logfile from memory and the GUI"""
        self.remove_logfile(logfile)
        self.known_logfiles = tuple(
            filter(lambda el: el != logfile, self.known_logfiles)
        )

        # Update the order so self.logfile_recent is updated
        self.update_logfile_order()

        self.update_logfile_list()
        self.update_buttonstate()

    def update_logfile_list(self) -> None:
        """Update the gui with the new list"""
        for frame, button, label, radiobutton in self.rows:
            label.destroy()
            radiobutton.destroy()
            button.destroy()
            frame.destroy()

        self.rows = []

        for recent, logfile in zip(self.logfile_recent, self.known_logfiles):
            frame = tk.Frame(self.logfile_list_frame)
            frame.pack(expand=True, fill=tk.X)
            button = tk.Button(
                frame,
                text="X",
                fg="red",
                command=functools.partial(self.remove_logfile_and_update, logfile),
            )
            button.pack(side=tk.LEFT)
            label = tk.Label(frame, text=logfile)
            label.pack(side=tk.LEFT)
            radiobutton = tk.Radiobutton(
                frame,
                variable=self.selected_logfile_var,
                value=logfile,
                bg="green" if recent else "grey",
                tristatevalue="<invalid_path>",
            )
            radiobutton.pack(side=tk.RIGHT)
            self.rows.append((frame, button, label, radiobutton))

    def submit_selection(self, selection: str | None = None) -> None:
        """Select the currently chosen logfile and exit"""
        self.choose_logfile(selection or self.selected_logfile_var.get())
        self.cancel_polling()
        self.root.destroy()

    def update_logfile_order(self) -> tuple[bool, bool]:
        """Update the order of the logfiles"""
        logfile_ages = tuple(
            time.time() - get_timestamp(file) for file in self.known_logfiles
        )

        # Keep most recent logfiles at the top
        aged_logfiles: list[tuple[float, str]] = sorted(
            zip(logfile_ages, self.known_logfiles), key=lambda item: item[0]
        )

        new_known_logfiles = tuple(logfile for timestamp, logfile in aged_logfiles)

        # True if logfile was updated recently
        new_logfile_recent = tuple(
            age < self.RECENT_TIMEOUT for age, logfile in aged_logfiles
        )

        if (
            self.autoselect_logfile
            and sum(new_logfile_recent) == 1  # One recent logfile
            and aged_logfiles[0][0] < 5  # It's really recent
            and new_known_logfiles[0] == self.last_used  # It's our last used logfile
            and self.last_used == self.selected_logfile_var.get()  # It's selected
        ):
            return False, True

        if (
            new_known_logfiles != self.known_logfiles
            or new_logfile_recent != self.logfile_recent
        ):
            self.known_logfiles = new_known_logfiles
            self.logfile_recent = new_logfile_recent

            return True, False

        return False, False

    def poll_logfile_timestamps(self) -> None:
        order_updated, autoselect = self.update_logfile_order()
        if autoselect:
            logger.info(f"Autoselected logfile {self.last_used}")
            self.submit_selection(self.last_used)
        else:
            if order_updated:
                self.update_logfile_list()
            self.task_id = self.root.after(1000, self.poll_logfile_timestamps)

    def cancel_polling(self) -> None:
        if self.task_id is not None:
            self.root.after_cancel(self.task_id)
            self.task_id = None

    def run(self) -> None:
        """Enter mainloop"""
        self.poll_logfile_timestamps()
        self.root.mainloop()


def prompt_for_logfile_path(
    logfile_cache_path: Path, autoselect_logfile: bool
) -> Path:  # pragma: nocover
    """Wait for the user to type /api new, or add an api key to their settings file"""

    try:
        logfile_cache = toml.load(logfile_cache_path)
    except Exception:
        logger.exception("Failed loading logfile cache")
        logfile_cache = {}

    logfile_cache_changed = False

    read_known_logfiles = logfile_cache.get("known_logfiles", None)
    if not isinstance(read_known_logfiles, (list, tuple)) or not all(
        isinstance(el, str) for el in read_known_logfiles
    ):
        read_known_logfiles = ()
        logfile_cache_changed = True

    known_logfiles = tuple(read_known_logfiles)

    # Add newly discovered logfiles
    new_logfiles = set(suggest_logfiles()) - set(known_logfiles)
    if new_logfiles:
        known_logfiles += tuple(new_logfiles)
        logfile_cache_changed = True

    # TODO: allow the logfile to stay, but indicate that it is not selectable
    if not all(map(file_exists, known_logfiles)):
        known_logfiles = tuple(filter(file_exists, known_logfiles))
        logfile_cache_changed = True

    last_used = logfile_cache.get("last_used", None)
    if not isinstance(last_used, str) or last_used not in known_logfiles:
        last_used = None
        logfile_cache_changed = True

    logfile_cache = {"known_logfiles": known_logfiles, "last_used": last_used}

    def write_cache() -> None:
        with logfile_cache_path.open("w") as cache_file:
            toml.dump(logfile_cache, cache_file)

    if logfile_cache_changed:
        write_cache()

    def remove_logfile(logfile: str) -> None:
        logfile_cache["known_logfiles"] = tuple(
            filter(lambda el: el != logfile, logfile_cache["known_logfiles"])
        )
        write_cache()

    def choose_logfile(logfile: str) -> None:
        if logfile not in logfile_cache["known_logfiles"]:
            logfile_cache["known_logfiles"] += (logfile,)
        logfile_cache["last_used"] = logfile
        write_cache()

    logfile_prompt = LogfilePrompt(
        known_logfiles=known_logfiles,
        last_used=last_used,
        autoselect_logfile=autoselect_logfile,
        remove_logfile=remove_logfile,
        choose_logfile=choose_logfile,
    )
    logfile_prompt.run()

    selected = logfile_cache["last_used"]
    logger.info(f"Selected logfile {selected}")

    if isinstance(selected, str):
        return Path(selected).resolve()

    sys.exit(1)
