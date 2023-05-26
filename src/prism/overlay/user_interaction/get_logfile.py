import functools
import logging
import sys
import tkinter as tk
import tkinter.filedialog
from pathlib import Path
from typing import Any

from prism.overlay.output.overlay.gui_components import ToggleButton
from prism.overlay.user_interaction.logfile_controller import (
    GUILogfile,
    LogfileController,
)
from prism.overlay.user_interaction.logfile_utils import (
    ActiveLogfile,
    LogfileCache,
    get_logfile,
    safe_resolve_existing_path,
)

logger = logging.getLogger(__name__)


class LogfilePrompt:  # pragma: nocover
    """Window to prompt the user to select a logfile"""

    def __init__(
        self,
        active_logfiles: tuple[ActiveLogfile, ...],
        last_used_id: int | None,
        autoselect: bool,
    ):
        self.logfile_controller = LogfileController.create(
            active_logfiles=active_logfiles,
            last_used_id=last_used_id,
            autoselect=autoselect,
            draw_logfile_list=self.draw_logfile_list,
            set_can_submit=self.set_can_submit,
        )

        self.task_id: str | None = None

        # Create a root window
        self.root = tk.Tk()
        self.root.title("Select a version")

        tk.Label(
            self.root,
            text="Select the logfile corresponding to the version you will be playing",
        ).pack()
        tk.Label(
            self.root, text="Versions not used for a long time are disabled", fg="red"
        ).pack()

        toggle_frame = tk.Frame(self.root)
        toggle_frame.pack()
        tk.Label(toggle_frame, text="Select inactive versions: ").pack(side=tk.LEFT)
        enable_inactive_versions_toggle = ToggleButton(
            toggle_frame,
            toggle_callback=self.logfile_controller.set_can_select_inactive,
            start_enabled=self.logfile_controller.can_select_inactive,
        )
        enable_inactive_versions_toggle.button.pack(side=tk.RIGHT)

        if autoselect and last_used_id is not None:
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
            value=last_used_id if last_used_id is not None else -1
        )
        self.selected_logfile_id_var.trace(
            "w", self.on_logfile_id_var_change
        )  # type: ignore [no-untyped-call]
        self.rows: list[tuple[tk.Frame, tk.Button, tk.Label, tk.Radiobutton]] = []

        self.submit_button = tk.Button(
            self.root,
            text="Submit",
            state=tk.DISABLED,
            command=self.submit_current_selection,
        )
        self.submit_button.pack()

        # Window close
        self.root.protocol("WM_DELETE_WINDOW", self.exit)

        self.root.update_idletasks()

        self.logfile_controller.update_gui()

    def exit(self) -> None:
        """Exit the overlay"""
        self.cancel_polling()
        sys.exit()

    def on_logfile_id_var_change(self, *args: Any, **kwargs: Any) -> None:
        """Forward changes to the logfile_id var to the controller"""
        self.logfile_controller.select_logfile(self.selected_logfile_id_var.get())

    def set_can_submit(self, can_submit: bool) -> None:
        """Update the buttonstate to match can_submit"""
        self.submit_button.configure(state=tk.NORMAL if can_submit else tk.DISABLED)

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

            self.submit_path(selected_path)

    def remove_logfile(self, logfile_id: int) -> None:
        """Remove the logfile from memory and the GUI"""
        self.logfile_controller.remove_logfile(logfile_id)

    def draw_logfile_list(self, gui_logfiles: tuple[GUILogfile, ...]) -> None:
        """Update the gui with the new list"""
        for frame, button, label, radiobutton in self.rows:
            label.destroy()
            radiobutton.destroy()
            button.destroy()
            frame.destroy()

        self.rows = []

        for gui_logfile in gui_logfiles:

            def on_label_click(
                e: "tk.Event[tk.Label]", id_: int = gui_logfile.id_
            ) -> None:
                self.selected_logfile_id_var.set(id_)

            frame = tk.Frame(self.logfile_list_frame)
            frame.pack(expand=True, fill=tk.X)

            button = tk.Button(
                frame,
                text="X",
                fg="red",
                command=functools.partial(self.remove_logfile, gui_logfile.id_),
            )
            button.pack(side=tk.LEFT)

            cursor = "hand2" if gui_logfile.selectable else "X_cursor"

            label = tk.Label(
                frame,
                text=gui_logfile.path_str,
                cursor=cursor,
                fg="black" if gui_logfile.recent else "gray",
            )
            if gui_logfile.selectable:
                label.bind("<Button-1>", on_label_click)
            label.pack(side=tk.LEFT)

            radiobutton = tk.Radiobutton(
                frame,
                variable=self.selected_logfile_id_var,
                value=gui_logfile.id_,
                bg="green" if gui_logfile.recent else "grey",
                tristatevalue="<invalid_path>",
                state=tk.NORMAL if gui_logfile.selectable else tk.DISABLED,
                cursor=cursor,
            )
            radiobutton.pack(side=tk.RIGHT)

            self.rows.append((frame, button, label, radiobutton))

    def poll_logfile_timestamps(self) -> None:
        """Refresh the state of the controller and schedule the next refresh"""
        autoselected = self.logfile_controller.refresh_state()
        if autoselected:
            logger.info("Selected logfile with autoselect")
            self.exit_with_submission()
            return

        self.schedule_polling()

    def schedule_polling(self) -> None:
        """Schedule the next refresh"""
        self.task_id = self.root.after(1000, self.poll_logfile_timestamps)

    def cancel_polling(self) -> None:
        """Cancel the next refresh"""
        if self.task_id is not None:
            self.root.after_cancel(self.task_id)
            self.task_id = None

    def submit_current_selection(self) -> None:
        """Submit the current selection if any"""
        submitted = self.logfile_controller.submit_current_selection()
        if submitted:
            logger.info("Selected logfile with submit button")
            self.exit_with_submission()

    def submit_path(self, path: Path) -> None:
        """Submit the given path"""
        logger.info("Selected logfile from file selection")
        self.logfile_controller.submit_path(path)
        self.exit_with_submission()

    def exit_with_submission(self, selected: Path | None = None) -> None:
        """Exit the GUI to return the selected logfile"""
        self.cancel_polling()
        self.root.destroy()

    def run(self) -> LogfileCache:
        """Run the GUI until the user has selected and return"""
        self.schedule_polling()
        self.root.mainloop()

        return self.logfile_controller.generate_result()


def prompt_for_logfile_path(
    logfile_cache_path: Path, autoselect: bool
) -> Path:  # pragma: nocover
    """Prompt the user to select a logfile"""

    def update_cache(
        active_logfiles: tuple[ActiveLogfile, ...], last_used_id: int | None
    ) -> LogfileCache:
        logfile_prompt = LogfilePrompt(
            active_logfiles=active_logfiles,
            last_used_id=last_used_id,
            autoselect=autoselect,
        )
        return logfile_prompt.run()

    try:
        logfile_path = get_logfile(
            update_cache=update_cache,
            logfile_cache_path=logfile_cache_path,
            autoselect=autoselect,
        )
    except ValueError:
        logger.exception("Failed getting logfile")
        sys.exit(1)

    if logfile_path is None:
        logger.info("User selected no logfile -> exiting")
        sys.exit()

    return logfile_path
