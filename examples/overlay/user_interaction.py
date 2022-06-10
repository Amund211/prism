import functools
import logging
import platform
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.filedialog
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import toml

from examples.overlay.parsing import NewAPIKeyEvent, parse_logline
from examples.overlay.settings import api_key_is_valid, read_settings

logger = logging.getLogger(__name__)


def watch_file_non_blocking_with_reopen(
    path: Path, timeout: float = 10
) -> Iterable[str | None]:
    """Iterate over all lines in a file. Reopen the file when stale."""
    while True:
        last_read = time.monotonic()
        with path.open("r", encoding="utf8", errors="replace") as f:
            while True:
                line = f.readline()
                if not line:
                    # No new lines -> wait
                    if time.monotonic() - last_read > timeout:
                        # More than `timeout` seconds since last read -> reopen file
                        logger.debug("Timed out reading file '{path}'; reopening")
                        break

                    yield None
                    time.sleep(0.1)
                    continue

                last_read = time.monotonic()
                yield line


class SearchLogfileForKeyThread(threading.Thread):
    """Thread that reads from the logfile to look for an API key"""

    def __init__(
        self,
        logfile_path: Path,
        key_found_event: threading.Event,
        key_queue: queue.Queue[str],
    ) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.logfile_path = logfile_path
        self.key_found_event = key_found_event
        self.key_queue = key_queue

    def run(self) -> None:
        """Read self.loglines until we find a new API key"""
        # True if we have read through the entire (present) file
        has_reached_end = False
        found_key: str | None = None

        for line in watch_file_non_blocking_with_reopen(self.logfile_path):
            if self.key_found_event.is_set():
                # The other thread found a new key
                return

            if line is None:
                has_reached_end = True
                if found_key is not None:
                    # The found key is the last key
                    self.key_found_event.set()
                    self.key_queue.put(found_key)
                    return
                continue

            event = parse_logline(line)

            if isinstance(event, NewAPIKeyEvent):
                # Store the found key
                found_key = event.key

                if has_reached_end:
                    # We have once reached the end of the logfile
                    # Assume this is the last key
                    self.key_found_event.set()
                    self.key_queue.put(found_key)
                    return


class SearchSettingsfileForKeyThread(threading.Thread):
    """Thread that reads from the settings file to look for an API key"""

    def __init__(
        self,
        settings_path: Path,
        key_found_event: threading.Event,
        key_queue: queue.Queue[str],
    ) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.settings_path = settings_path
        self.key_found_event = key_found_event
        self.key_queue = key_queue

    def run(self) -> None:
        """Periodically read settings file until we find a new API key"""
        while not self.key_found_event.is_set():
            try:
                settings_object = read_settings(self.settings_path)
            except (OSError, ValueError) as e:
                logger.debug(
                    f"Exception caught in search settings thread: {e}. Ignoring"
                )
                time.sleep(5)
            else:
                key = settings_object.get("hypixel_api_key", None)
                if isinstance(key, str) and api_key_is_valid(key):
                    self.key_found_event.set()
                    self.key_queue.put(key)
                    return

            time.sleep(1)


class APIKeyPrompt:
    """Window to prompt the user to type /api new or edit their settings"""

    def __init__(self, settings_path_str: str, key_found_event: threading.Event):
        self.key_found_event = key_found_event

        # Create a root window
        self.root = tk.Tk()
        self.root.title("Set a Hypixel API key")

        tk.Label(
            self.root,
            text="You have not set an API key - keep this window open.",
            fg="red",
        ).pack()

        tk.Label(
            self.root,
            text=(
                "To set an API key you can either:\n"
                "1. Log onto Hypixel and type '/api new' in the chat\n"
                f"2. Open your settings file at {settings_path_str} and add "
                "an existing key there"
            ),
        ).pack()

        # sys.exit() if the user quits the window, otherwise we would get stuck at
        # *_thread.join()
        # Cancel button
        tk.Button(self.root, text="Cancel", command=sys.exit).pack()

        # Window close
        self.root.protocol("WM_DELETE_WINDOW", sys.exit)

        self.root.update_idletasks()

    def look_for_key(self) -> None:
        """Check if a key has been found"""
        if self.key_found_event.is_set():
            # A key has been found -> exit the mainloop
            self.root.destroy()
            return

        self.root.after(100, self.look_for_key)

    def run(self) -> None:
        """Enter mainloop and start polling for found keys"""
        self.root.after(100, self.look_for_key)
        self.root.mainloop()


def wait_for_api_key(logfile_path: Path, settings_path: Path) -> str:
    """Wait for the user to type /api new, or add an api key to their settings file"""

    # Queue to communicate found keys
    key_queue = queue.Queue[str]()
    # Event to communicate a key being found
    key_found_event = threading.Event()

    # Search in the logfile
    logfile_thread = SearchLogfileForKeyThread(
        logfile_path=logfile_path, key_found_event=key_found_event, key_queue=key_queue
    )
    logfile_thread.start()

    # Search in the settings
    settings_thread = SearchSettingsfileForKeyThread(
        settings_path=settings_path,
        key_found_event=key_found_event,
        key_queue=key_queue,
    )
    settings_thread.start()

    key_prompt = APIKeyPrompt(
        settings_path_str=str(settings_path), key_found_event=key_found_event
    )
    key_prompt.run()

    # Wait for both threads to finish (the other exits as soon as one finds a key)
    logfile_thread.join()
    settings_thread.join()

    new_key = key_queue.get_nowait()

    return new_key


class LogfilePrompt:
    """Window to prompt the user to select a logfile"""

    def __init__(
        self,
        known_logfiles: Sequence[str],
        last_used: str | None,
        remove_logfile: Callable[[str], None],
        choose_logfile: Callable[[str], None],
    ):
        self.known_logfiles = known_logfiles
        self.last_used = last_used
        self.remove_logfile = remove_logfile
        self.choose_logfile = choose_logfile

        # Create a root window
        self.root = tk.Tk()
        self.root.title("Select a version")

        tk.Label(
            self.root,
            text="Select the logfile corresponding to the version you will be playing",
        ).pack()

        tk.Button(
            self.root, text="Select a new file", command=self.make_selection
        ).pack()

        self.logfile_list_frame = tk.Frame()
        self.logfile_list_frame.pack()
        self.selected_logfile_var = tk.StringVar(value=self.last_used)
        self.selected_logfile_var.trace("w", self.update_buttonstate)  # type: ignore
        self.rows: list[tuple[tk.Frame, tk.Button, tk.Label, tk.Radiobutton]] = []

        self.update_logfile_list()

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

        # Window close
        self.root.protocol("WM_DELETE_WINDOW", sys.exit)

        self.root.update_idletasks()

    def update_buttonstate(self, *args: Any, **kwargs: Any) -> None:
        self.submit_button.configure(
            state=tk.DISABLED
            if self.selected_logfile_var.get() not in self.known_logfiles
            else tk.NORMAL
        )

    def make_selection(self) -> None:
        result = tk.filedialog.askopenfilename(
            parent=self.root,
            title="Select launcher_log.txt",
            filetypes=(
                ("Text/log", ".txt .log"),
                ("Vanilla logfile", "launcher_log.txt"),
            ),
        )

        if result is not None:
            self.submit_selection(result)

    def remove_logfile_and_update(self, logfile: str) -> None:
        """Remove the logfile from memory and the GUI"""
        self.remove_logfile(logfile)
        self.known_logfiles = list(
            filter(lambda el: el != logfile, self.known_logfiles)
        )
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

        for logfile in self.known_logfiles:
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
                frame, variable=self.selected_logfile_var, value=logfile
            )
            radiobutton.pack(side=tk.RIGHT)
            self.rows.append((frame, button, label, radiobutton))

    def submit_selection(self, selection: str | None = None) -> None:
        """Select the currently chosen logfile and exit"""
        self.choose_logfile(selection or self.selected_logfile_var.get())
        self.root.destroy()

    def run(self) -> None:
        """Enter mainloop"""
        self.root.mainloop()


def suggest_logfile_candidates() -> list[Path]:
    system = platform.system()
    if system == "Linux":
        vanilla_logfile = Path.home() / ".minecraft" / "launcher_log.txt"
        return [vanilla_logfile]
    elif system == "Darwin":
        vanilla_logfile = (
            Path.home()
            / "Library"
            / "Application Support"
            / "minecraft"
            / "launcher_log.txt"
        )
        return [vanilla_logfile]
    elif system == "Windows":
        try:
            lunar_client_logfiles = tuple(
                (Path.home() / ".lunarclient" / "offline").rglob("latest.log")
            )
        except OSError:
            lunar_client_logfiles = ()

        return [
            *lunar_client_logfiles,
            Path.home() / "AppData" / "Roaming" / ".minecraft" / "launcher_log.txt",
        ]
    else:
        # system == "Java"
        return []


def suggest_logfiles() -> list[str]:
    valid_logfiles: list[str] = []

    for logpath in suggest_logfile_candidates():
        try:
            if logpath.is_file():
                valid_logfiles.append(str(logpath.resolve()))
        except OSError:
            pass

    return valid_logfiles


def prompt_for_logfile_path(logfile_cache_path: Path) -> Path:
    """Wait for the user to type /api new, or add an api key to their settings file"""

    try:
        logfile_cache = toml.load(logfile_cache_path)
    except Exception:
        logfile_cache = {}

    known_logfiles = logfile_cache.get("known_logfiles", None)
    if not isinstance(known_logfiles, list) or not all(
        isinstance(el, str) for el in known_logfiles
    ):
        known_logfiles = []

    if not known_logfiles:
        known_logfiles = suggest_logfiles()

    last_used = logfile_cache.get("last_used", None)
    if not isinstance(last_used, str) or last_used not in known_logfiles:
        last_used = known_logfiles[0] if len(known_logfiles) > 0 else None

    logfile_cache = {"known_logfiles": known_logfiles, "last_used": last_used}

    def write_cache() -> None:
        with logfile_cache_path.open("w") as cache_file:
            toml.dump(logfile_cache, cache_file)

    def remove_logfile(logfile: str) -> None:
        logfile_cache["known_logfiles"] = list(
            filter(lambda el: el != logfile, logfile_cache["known_logfiles"])
        )
        write_cache()

    def choose_logfile(logfile: str) -> None:
        if logfile not in logfile_cache["known_logfiles"]:
            logfile_cache["known_logfiles"].append(logfile)
        logfile_cache["last_used"] = logfile
        write_cache()

    logfile_prompt = LogfilePrompt(
        known_logfiles=known_logfiles,
        last_used=last_used,
        remove_logfile=remove_logfile,
        choose_logfile=choose_logfile,
    )
    logfile_prompt.run()

    selected = logfile_cache["last_used"]

    if isinstance(selected, str):
        return Path(selected).resolve()

    sys.exit(1)
