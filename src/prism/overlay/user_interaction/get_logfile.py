import functools
import logging
import sys
import tkinter as tk
import tkinter.filedialog
from pathlib import Path
from typing import Any

from prism.overlay.user_interaction.logfile_utils import (
    ActiveLogfile,
    LogfileCache,
    autoselect_logfile,
    compare_active_logfiles,
    create_active_logfiles,
    read_logfile_cache,
    refresh_active_logfiles,
    safe_resolve_existing_path,
    suggest_logfiles,
    write_logfile_cache,
)

logger = logging.getLogger(__name__)


class LogfilePrompt:  # pragma: nocover
    """Window to prompt the user to select a logfile"""

    def __init__(self, cache: LogfileCache, autoselect_logfile: bool):
        self.cache = cache
        self.autoselect_logfile = autoselect_logfile

        self.last_used_id = cache.last_used_index
        self.active_logfiles = create_active_logfiles(cache.known_logfiles)

        # Reset the last used index as we use this to return the new selection
        self.cache.last_used_index = None

        self.logfile_id_map = {
            active_logfile.id_: active_logfile
            for active_logfile in self.active_logfiles
        }

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

        if self.autoselect_logfile and self.last_used_id is not None:
            tk.Label(
                self.root,
                text=(
                    "Your last used version will be "
                    "automatically selected when available"
                ),
                fg="green",
            ).pack()

        tk.Button(
            self.root, text="Select a new file", command=self.select_from_filesystem
        ).pack()

        self.logfile_list_frame = tk.Frame()
        self.logfile_list_frame.pack()
        self.selected_logfile_id_var = tk.IntVar(
            value=self.last_used_id if self.last_used_id is not None else -1
        )
        self.selected_logfile_id_var.trace(
            "w", self.update_buttonstate
        )  # type: ignore [no-untyped-call]
        self.rows: list[tuple[tk.Frame, tk.Button, tk.Label, tk.Radiobutton]] = []

        self.submit_button = tk.Button(
            self.root,
            text="Submit",
            state=tk.DISABLED,
            command=self.submit,
        )
        self.submit_button.pack()
        self.update_buttonstate()

        # Cancel button
        tk.Button(self.root, text="Cancel", command=self.exit).pack()

        # Window close
        self.root.protocol("WM_DELETE_WINDOW", self.exit)

        self.root.update_idletasks()

        self.update_logfile_list()

    def exit(self) -> None:
        self.cancel_polling()
        sys.exit()

    def get_active_logfile_by_id(self, id_: int) -> ActiveLogfile | None:
        """Get the ActiveLogfile instance with the given id if it exists"""
        return self.logfile_id_map.get(id_, None)

    def update_buttonstate(self, *args: Any, **kwargs: Any) -> None:
        """Disabled the button if the user has not selected a valid, recent logfile"""
        selected_logfile = self.get_active_logfile_by_id(
            self.selected_logfile_id_var.get()
        )
        self.submit_button.configure(
            state=tk.DISABLED if selected_logfile is None else tk.NORMAL
        )

    def select_from_filesystem(self) -> None:
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
            selected_path = safe_resolve_existing_path(result)
            if selected_path is None:
                logger.error(f"Could not resolve user's selection {result}")
                return

            self.submit(selected_path)

    def remove_logfile(self, logfile_id: int) -> None:
        """Remove the logfile from memory and the GUI"""
        self.active_logfiles = tuple(
            filter(
                lambda active_logfile: active_logfile.id_ != logfile_id,
                self.active_logfiles,
            )
        )
        self.logfile_id_map.pop(logfile_id, None)

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

        for active_logfile in self.active_logfiles:
            frame = tk.Frame(self.logfile_list_frame)
            frame.pack(expand=True, fill=tk.X)
            button = tk.Button(
                frame,
                text="X",
                fg="red",
                command=functools.partial(self.remove_logfile, active_logfile.id_),
            )
            button.pack(side=tk.LEFT)
            label = tk.Label(frame, text=str(active_logfile.path))
            label.pack(side=tk.LEFT)
            radiobutton = tk.Radiobutton(
                frame,
                variable=self.selected_logfile_id_var,
                value=active_logfile.id_,
                bg="green" if active_logfile.recent else "grey",
                tristatevalue="<invalid_path>",
            )
            radiobutton.pack(side=tk.RIGHT)
            self.rows.append((frame, button, label, radiobutton))

    def submit(self, selected: Path | None = None) -> None:
        """Select the currently chosen logfile and exit"""
        self.cache.known_logfiles = tuple(
            active_logfile.path for active_logfile in self.active_logfiles
        )

        if selected is None:
            # If the user submitted with the button use the checked logfile
            selected_logfile = self.get_active_logfile_by_id(
                self.selected_logfile_id_var.get()
            )
            if selected_logfile is not None:
                selected = selected_logfile.path
            else:
                logger.error(
                    f"Call to submit_selection failed: {selected=} "
                    f"{self.selected_logfile_id_var.get()=}"
                    f"{self.logfile_id_map=}"
                )
                return

        try:
            self.cache.last_used_index = self.cache.known_logfiles.index(selected)
        except ValueError:
            logger.exception(
                f"Could not find {selected} in {self.cache.known_logfiles}"
            )
            return

        self.cancel_polling()
        self.root.destroy()

    def refresh_logfile_ages(self) -> tuple[bool, ActiveLogfile | None]:
        """Update the order of the logfiles"""
        old_active_logfiles = self.active_logfiles
        self.active_logfiles = refresh_active_logfiles(self.active_logfiles)

        if self.autoselect_logfile:
            autoselected = autoselect_logfile(
                self.active_logfiles,
                selected_id=self.selected_logfile_id_var.get(),
                last_used_id=self.last_used_id,
            )
            if autoselected is not None:
                return False, autoselected

        if not compare_active_logfiles(old_active_logfiles, self.active_logfiles):
            # The order, or some properties, changed
            return True, None

        return False, None

    def poll_logfile_timestamps(self) -> None:
        order_updated, autoselected = self.refresh_logfile_ages()
        if autoselected is not None:
            logger.info(f"Autoselected logfile {autoselected.path}")
            self.submit(autoselected.path)
            return

        if order_updated:
            self.update_logfile_list()

        self.schedule_polling()

    def schedule_polling(self) -> None:
        self.task_id = self.root.after(1000, self.poll_logfile_timestamps)

    def cancel_polling(self) -> None:
        if self.task_id is not None:
            self.root.after_cancel(self.task_id)
            self.task_id = None

    def run(self) -> None:
        """Enter mainloop"""
        self.schedule_polling()
        self.root.mainloop()


def prompt_for_logfile_path(
    logfile_cache_path: Path, autoselect_logfile: bool
) -> Path:  # pragma: nocover
    """Prompt the user to select a logfile"""
    cache, logfile_cache_updated = read_logfile_cache(logfile_cache_path)
    old_known_logfiles = cache.known_logfiles
    old_last_used_index = cache.last_used_index

    # Add newly discovered logfiles
    new_logfiles = set(suggest_logfiles()) - set(cache.known_logfiles)
    if new_logfiles:
        cache.known_logfiles += tuple(new_logfiles)

    # The cache is updated with the user's selection in LogfilePrompt
    logfile_prompt = LogfilePrompt(cache=cache, autoselect_logfile=autoselect_logfile)
    logfile_prompt.run()

    if (
        cache.known_logfiles != old_known_logfiles
        or cache.last_used_index != old_last_used_index
        or logfile_cache_updated
    ):
        write_logfile_cache(logfile_cache_path, cache)

    selected_index = cache.last_used_index

    if selected_index is None:
        logger.info("User selected no logfile -> exiting")
        sys.exit()

    if 0 <= selected_index < len(cache.known_logfiles):
        selected = cache.known_logfiles[selected_index]
        logger.info(f"Selected logfile {selected}")
        return selected
    else:
        logger.error(f"Selected index out of range! {cache}")
        sys.exit(1)
