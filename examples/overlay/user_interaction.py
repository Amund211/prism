import functools
import logging
import platform
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.filedialog
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

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

    # Number of seconds for a logfile to be considered recently used
    RECENT_TIMEOUT = 60

    def __init__(
        self,
        known_logfiles: tuple[str, ...],
        last_used: str | None,
        remove_logfile: Callable[[str], None],
        choose_logfile: Callable[[str], None],
    ):
        self.known_logfiles = known_logfiles
        self.last_used = last_used
        self.remove_logfile = remove_logfile
        self.choose_logfile = choose_logfile

        self.logfile_recent = tuple(False for logfile in self.known_logfiles)
        self.update_logfile_order()

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

        def on_close() -> None:
            self.cancel_polling()
            sys.exit()

        # Window close
        self.root.protocol("WM_DELETE_WINDOW", on_close)

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
            )
            radiobutton.pack(side=tk.RIGHT)
            self.rows.append((frame, button, label, radiobutton))

    def submit_selection(self, selection: str | None = None) -> None:
        """Select the currently chosen logfile and exit"""
        self.choose_logfile(selection or self.selected_logfile_var.get())
        self.cancel_polling()
        self.root.destroy()

    def update_logfile_order(self) -> bool:
        """Update the order of the logfiles"""
        now = time.time()
        logfile_timestamps = tuple(map(get_timestamp, self.known_logfiles))

        # Keep most recent logfiles at the top
        timestamped_logfiles: list[tuple[float, str]] = sorted(
            zip(logfile_timestamps, self.known_logfiles),
            key=lambda item: item[0],
            reverse=True,
        )

        sorted_logfile_timestamps = tuple(
            timestamp for timestamp, logfile in timestamped_logfiles
        )
        new_known_logfiles = tuple(
            logfile for timestamp, logfile in timestamped_logfiles
        )

        # True if logfile was updated recently
        new_logfile_recent = tuple(
            now - timestamp < self.RECENT_TIMEOUT
            for timestamp in sorted_logfile_timestamps
        )

        if (
            new_known_logfiles != self.known_logfiles
            or new_logfile_recent != self.logfile_recent
        ):
            self.known_logfiles = new_known_logfiles
            self.logfile_recent = new_logfile_recent

            return True

        return False

    def poll_logfile_timestamps(self) -> None:
        order_updated = self.update_logfile_order()
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


def file_exists(path: Path | str) -> bool:
    """Return True if the file exists"""
    if isinstance(path, str):
        path = Path(path)

    try:
        return path.is_file()
    except OSError:
        return False


def suggest_logfiles() -> tuple[str, ...]:
    """Suggest logfile candidates that exist"""
    return tuple(map(str, filter(file_exists, suggest_logfile_candidates())))


def get_timestamp(path_str: str) -> float:
    """Get the modified timestamp of the file"""
    try:
        stat = Path(path_str).stat()
    except OSError:
        return 0
    else:
        return stat.st_mtime


def prompt_for_logfile_path(logfile_cache_path: Path) -> Path:
    """Wait for the user to type /api new, or add an api key to their settings file"""

    try:
        logfile_cache = toml.load(logfile_cache_path)
    except Exception:
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
        last_used = known_logfiles[0] if len(known_logfiles) > 0 else None
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
