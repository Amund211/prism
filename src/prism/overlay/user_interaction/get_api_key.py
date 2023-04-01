import logging
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.filedialog
from pathlib import Path

from prism.overlay.events import NewAPIKeyEvent
from prism.overlay.file_utils import watch_file_with_reopen
from prism.overlay.parsing import parse_logline
from prism.overlay.settings import api_key_is_valid, read_settings

logger = logging.getLogger(__name__)


def search_logfile_for_key(
    logfile_path: Path, key_found_event: threading.Event
) -> str | None:
    """Read self.loglines until we find a new API key"""
    # True if we have read through the entire (present) file
    has_reached_end = False
    found_key: str | None = None

    for line in watch_file_with_reopen(logfile_path, start_at=0, blocking=False):
        if key_found_event.is_set():
            # The other thread found a new key
            return None

        if line is None:
            has_reached_end = True
            if found_key is not None:
                # The found key is the last key
                return found_key
            continue

        event = parse_logline(line)

        if isinstance(event, NewAPIKeyEvent):
            # Store the found key
            found_key = event.key

            if has_reached_end:
                # We have once reached the end of the logfile
                # Assume this is the last key
                return found_key
    return None  # pragma: nocover (unreachable)


class SearchLogfileForKeyThread(threading.Thread):  # pragma: nocover
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
        found_key = search_logfile_for_key(self.logfile_path, self.key_found_event)
        if found_key is not None:
            # Our thread found the key -> notify
            self.key_found_event.set()
            self.key_queue.put(found_key)


def search_settings_file_for_key(
    settings_path: Path, key_found_event: threading.Event
) -> str | None:
    """Periodically read settings file until we find a new API key"""
    while not key_found_event.is_set():
        try:
            settings_object = read_settings(settings_path)
        except (OSError, ValueError):
            logger.exception("Exception caught in search settings thread. Ignoring")
            time.sleep(4)
        else:
            found_key = settings_object.get("hypixel_api_key", None)
            if isinstance(found_key, str) and api_key_is_valid(found_key):
                return found_key

        time.sleep(1)
    return None


class SearchSettingsfileForKeyThread(threading.Thread):  # pragma: nocover
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
        found_key = search_settings_file_for_key(
            self.settings_path, self.key_found_event
        )
        if found_key is not None:
            # Our thread found the key -> notify
            self.key_found_event.set()
            self.key_queue.put(found_key)


class APIKeyPrompt:  # pragma: nocover
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


def wait_for_api_key(logfile_path: Path, settings_path: Path) -> str:  # pragma: nocover
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
