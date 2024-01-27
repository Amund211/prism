import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Self

from prism.overlay.user_interaction.logfile_utils import (
    ActiveLogfile,
    LogfileCache,
    autoselect_logfile,
    refresh_active_logfiles,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GUILogfile:
    id_: int
    path_str: str
    recent: bool
    selectable: bool


@dataclass
class LogfileController:
    # State
    active_logfiles: tuple[ActiveLogfile, ...]
    last_used_id: int | None
    selected_id: int | None
    can_select_inactive: bool
    autoselect: bool

    # Path submitted from submit_path or submit_current_selection
    submitted_path: Path | None

    # Cached results from drawing and setting can_submit
    last_render: tuple[GUILogfile, ...] | None
    can_submit: bool | None

    # Callbacks
    draw_logfile_list: Callable[[tuple[GUILogfile, ...]], None]
    set_can_submit: Callable[[bool], None]

    @classmethod
    def create(
        cls,
        active_logfiles: tuple[ActiveLogfile, ...],
        last_used_id: int | None,
        autoselect: bool,
        draw_logfile_list: Callable[[tuple[GUILogfile, ...]], None],
        set_can_submit: Callable[[bool], None],
    ) -> Self:
        """Create a LogfileController and initialize the state"""
        return cls(
            # Parameters
            active_logfiles=active_logfiles,
            last_used_id=last_used_id,
            selected_id=last_used_id,
            autoselect=autoselect,
            draw_logfile_list=draw_logfile_list,
            set_can_submit=set_can_submit,
            # Don't allow selecting inactive logfiles by default
            can_select_inactive=False,
            # Cache and output variables
            submitted_path=None,
            last_render=None,
            can_submit=None,
        )

    def set_can_select_inactive(self, can_select_inactive: bool) -> None:
        """Set whether the user can select inactive logfiles"""
        logger.info(f"Setting {can_select_inactive=}")
        self.can_select_inactive = can_select_inactive
        self._update_can_submit()
        self._update_logfile_list()

    def select_logfile(self, id_: int) -> None:
        """Select the logfile with the given id"""

        logger.info(f"Selecting logfile with id {id_}")

        if self._get_active_logfile_by_id(id_) is not None:
            self.selected_id = id_
        else:
            logger.error("Tried selecting missing logfile")
            self.selected_id = None

        self._update_can_submit()

    def remove_logfile(self, id_: int) -> None:
        """Remove the logfile with the given id"""
        logger.info(f"Removing logfile with id {id_}")

        if self.selected_id == id_:
            logger.info("Removed current selection, updating can_submit")
            self.selected_id = None
            self._update_can_submit()

        self.active_logfiles = tuple(
            filter(
                lambda active_logfile: active_logfile.id_ != id_,
                self.active_logfiles,
            )
        )

        self._update_logfile_list()

    def submit_current_selection(self) -> bool:
        """Submit the currently selected logfile, return True if submitted"""
        logger.info("Submitting current selection")

        if not self.can_submit:
            logger.error("Tried to submit with self.can_submit False")
            return False

        if self.selected_id is None:  # pragma: no coverage
            logger.error("Tried to submit without a selection")
            return False

        selected_logfile = self._get_active_logfile_by_id(self.selected_id)
        if selected_logfile is None:  # pragma: no coverage
            logger.error("Tried to submit with a missing logfile")
            return False

        self.submitted_path = selected_logfile.path
        return True

    def submit_path(self, path: Path) -> None:
        """Submit the given path"""
        logger.info(f"Submitting given path {path}")
        self.submitted_path = path

    def refresh_state(self) -> bool:
        """
        Refresh the logfile ages and perform necessary callbacks

        Return True if a logfile has been autoselected
        """
        self.active_logfiles = refresh_active_logfiles(self.active_logfiles)

        if self.autoselect:
            autoselected = autoselect_logfile(self.active_logfiles)
            if autoselected is not None:
                logger.info(f"Autoselected logfile {autoselected.path}")
                self.submit_path(autoselected.path)
                return True

        self._update_logfile_list()
        self._update_can_submit()

        return False

    def generate_result(self) -> LogfileCache:
        """Generate the new logfile cache based on the current state"""
        logger.info("Generating result for logfile selection")

        known_logfiles = tuple(
            active_logfile.path for active_logfile in self.active_logfiles
        )
        last_used_index = None
        if self.submitted_path is not None:
            try:
                last_used_index = known_logfiles.index(self.submitted_path)
            except ValueError:
                known_logfiles += (self.submitted_path,)
                last_used_index = len(known_logfiles) - 1

        return LogfileCache(
            known_logfiles=known_logfiles, last_used_index=last_used_index
        )

    def update_gui(self) -> None:
        """Update the logfile list and can_submit"""
        logger.info("Call to update_gui")
        self._update_logfile_list()
        self._update_can_submit()

    def _update_logfile_list(self) -> None:
        """Redraw the logfile list if necessary"""
        new_render = self._render_gui_logfiles()
        if self.last_render == new_render:
            return

        logger.info("Updating GUI logfile list")

        self.draw_logfile_list(new_render)
        self.last_render = new_render

    def _update_can_submit(self) -> None:
        """Set can_submit if necessary"""
        can_submit = (
            self._can_select_logfile_with_id(self.selected_id)
            if self.selected_id is not None
            else False
        )

        if self.can_submit != can_submit:
            logger.info("Updating GUI can_submit")
            self.can_submit = can_submit
            self.set_can_submit(can_submit)

    def _get_active_logfile_by_id(self, id_: int) -> ActiveLogfile | None:
        """Return the active logfile with the given id, or None if not found"""
        try:
            return next(
                filter(
                    lambda active_logfile: active_logfile.id_ == id_,
                    self.active_logfiles,
                )
            )
        except StopIteration:
            return None

    def _can_select_logfile(self, active_logfile: ActiveLogfile) -> bool:
        """Return True if the given logfile can be selected"""
        return active_logfile.recent or self.can_select_inactive

    def _can_select_logfile_with_id(self, id_: int) -> bool:
        """Return True if the logfile with the given id can be selected"""
        active_logfile = self._get_active_logfile_by_id(id_)
        if active_logfile is None:
            return False
        return self._can_select_logfile(active_logfile)

    def _render_gui_logfiles(self) -> tuple[GUILogfile, ...]:
        """Render the ActiveLogfiles to a tuple of GUILogfiles"""
        return tuple(
            GUILogfile(
                id_=active_logfile.id_,
                path_str=str(active_logfile.path),
                selectable=self._can_select_logfile(active_logfile),
                recent=active_logfile.recent,
            )
            for active_logfile in self.active_logfiles
        )
