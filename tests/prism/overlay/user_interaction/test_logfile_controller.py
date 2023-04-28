import unittest.mock
from collections.abc import Set
from dataclasses import replace
from pathlib import Path

from prism.overlay.user_interaction.logfile_controller import LogfileController
from prism.overlay.user_interaction.logfile_utils import ActiveLogfile, LogfileCache

DEFAULT_ACTIVE_LOGFILES = (
    ActiveLogfile(id_=0, path=Path("somepath"), age_seconds=10),
    ActiveLogfile(id_=1, path=Path("old_logfile"), age_seconds=12345),
    ActiveLogfile(id_=2, path=Path("older_logfile"), age_seconds=123456),
    ActiveLogfile(id_=3, path=Path("oldest_logfile"), age_seconds=1234567),
)


def paths_from_active_logfiles(
    active_logfiles: tuple[ActiveLogfile, ...]
) -> tuple[Path, ...]:
    return tuple(active_logfile.path for active_logfile in active_logfiles)


DEFAULT_PATHS = paths_from_active_logfiles(DEFAULT_ACTIVE_LOGFILES)


def create_logfile_controller(
    active_logfiles: tuple[ActiveLogfile, ...] = DEFAULT_ACTIVE_LOGFILES,
    last_used_id: int | None = 0,
    autoselect: bool = True,
) -> LogfileController:
    logfile_controller = LogfileController.create(
        active_logfiles=active_logfiles,
        last_used_id=last_used_id,
        autoselect=autoselect,
        draw_logfile_list=unittest.mock.MagicMock(),
        set_can_submit=unittest.mock.MagicMock(),
    )

    # The GUI calls this on init
    logfile_controller.update_gui()

    logfile_controller.draw_logfile_list.reset_mock()  # type: ignore [attr-defined]
    logfile_controller.set_can_submit.reset_mock()  # type: ignore [attr-defined]

    return logfile_controller


def assert_called_update_logfile_list(logfile_controller: LogfileController) -> None:
    logfile_controller.draw_logfile_list.assert_called_once()  # type: ignore [attr-defined]  # noqa: E501
    logfile_controller.draw_logfile_list.reset_mock()  # type: ignore [attr-defined]


def assert_didnt_call_update_logfile_list(
    logfile_controller: LogfileController,
) -> None:
    logfile_controller.draw_logfile_list.assert_not_called()  # type: ignore [attr-defined]  # noqa: E501


def assert_called_set_can_submit(logfile_controller: LogfileController) -> None:
    logfile_controller.set_can_submit.assert_called_once()  # type: ignore [attr-defined]  # noqa: E501
    logfile_controller.set_can_submit.reset_mock()  # type: ignore [attr-defined]


def assert_didnt_call_set_can_submit(logfile_controller: LogfileController) -> None:
    logfile_controller.set_can_submit.assert_not_called()  # type: ignore [attr-defined]


def call_refresh_state(
    logfile_controller: LogfileController,
    *,
    updated_logfiles: Set[int] = frozenset(),
    time_since_last_refresh: float = 1,
) -> bool:
    """
    Call refresh_state on the logfile controller

    The calls to refresh_age are patched so that there is no disk I/O, but the
    ages are incremented by time_since_last_refresh or reset to 0
    """

    def refresh_age(self: ActiveLogfile) -> ActiveLogfile:
        return replace(
            self,
            age_seconds=0
            if self.id_ in updated_logfiles
            else self.age_seconds + time_since_last_refresh,
        )

    with unittest.mock.patch.object(ActiveLogfile, "refresh_age", refresh_age):
        return logfile_controller.refresh_state()


def compare_result(
    cache: LogfileCache, paths: tuple[Path, ...], last_used_index: int | None
) -> None:
    """Assert that the cache contents matches the paths and last_used_index unordered"""
    assert set(cache.known_logfiles) == set(paths)
    assert cache.last_used_index == last_used_index


def test_logfile_controller_autoselection() -> None:
    logfile_controller = create_logfile_controller(last_used_id=0)

    compare_result(
        logfile_controller.generate_result(), DEFAULT_PATHS, last_used_index=None
    )

    # Refresh where nothing happened
    assert not call_refresh_state(logfile_controller)
    compare_result(
        logfile_controller.generate_result(), DEFAULT_PATHS, last_used_index=None
    )
    assert_didnt_call_update_logfile_list(logfile_controller)

    # A logfile became active, but it is not our last used one
    assert not call_refresh_state(logfile_controller, updated_logfiles={1})
    compare_result(
        logfile_controller.generate_result(), DEFAULT_PATHS, last_used_index=None
    )
    assert_called_update_logfile_list(logfile_controller)

    # Our last used logfile became active, but it is not the only recent one
    assert not call_refresh_state(
        logfile_controller, updated_logfiles={0}, time_since_last_refresh=60
    )
    compare_result(
        logfile_controller.generate_result(), DEFAULT_PATHS, last_used_index=None
    )
    assert_called_update_logfile_list(logfile_controller)

    # Our last used logfile is active and is the only recent one
    assert call_refresh_state(logfile_controller)
    compare_result(
        logfile_controller.generate_result(), DEFAULT_PATHS, last_used_index=0
    )
    assert_didnt_call_update_logfile_list(logfile_controller)

    # We were always able to submit
    assert_didnt_call_set_can_submit(logfile_controller)


def test_can_select_inactive() -> None:
    logfile_controller = create_logfile_controller(last_used_id=1, autoselect=False)

    # The current selection is inactive
    assert not logfile_controller.submit_current_selection()
    assert not logfile_controller.can_submit

    logfile_controller.set_can_select_inactive(True)
    assert logfile_controller.can_submit
    assert_called_update_logfile_list(logfile_controller)
    assert_called_set_can_submit(logfile_controller)

    logfile_controller.set_can_select_inactive(False)
    assert not logfile_controller.submit_current_selection()
    assert not logfile_controller.can_submit
    assert_called_update_logfile_list(logfile_controller)
    assert_called_set_can_submit(logfile_controller)

    logfile_controller.set_can_select_inactive(True)
    assert logfile_controller.can_submit
    assert_called_update_logfile_list(logfile_controller)
    assert_called_set_can_submit(logfile_controller)

    assert logfile_controller.submit_current_selection()
    compare_result(
        logfile_controller.generate_result(),
        paths_from_active_logfiles(DEFAULT_ACTIVE_LOGFILES),
        last_used_index=1,
    )


def test_can_select_inactive_short_list() -> None:
    logfile_controller = create_logfile_controller(
        active_logfiles=DEFAULT_ACTIVE_LOGFILES[:1], last_used_id=0
    )

    logfile_controller.set_can_select_inactive(True)
    # No unnecessary GUI updates
    assert_didnt_call_update_logfile_list(logfile_controller)
    assert_didnt_call_set_can_submit(logfile_controller)

    logfile_controller.set_can_select_inactive(False)
    # No unnecessary GUI updates
    assert_didnt_call_update_logfile_list(logfile_controller)
    assert_didnt_call_set_can_submit(logfile_controller)


def test_select_logfile() -> None:
    active_logfiles = (
        ActiveLogfile(id_=0, path=Path("path1"), age_seconds=10),
        ActiveLogfile(id_=1, path=Path("path2"), age_seconds=11),
        ActiveLogfile(id_=2, path=Path("path3"), age_seconds=11111),
    )
    paths = paths_from_active_logfiles(active_logfiles)

    logfile_controller = create_logfile_controller(
        last_used_id=None,
        active_logfiles=active_logfiles,
        autoselect=False,
    )

    # No initial selection
    assert not logfile_controller.can_submit
    assert not logfile_controller.submit_current_selection()
    compare_result(logfile_controller.generate_result(), paths, last_used_index=None)

    logfile_controller.select_logfile(0)
    assert logfile_controller.can_submit
    compare_result(logfile_controller.generate_result(), paths, last_used_index=None)
    assert_called_set_can_submit(logfile_controller)

    # Inactive logfile, not selectable
    logfile_controller.select_logfile(2)
    assert not logfile_controller.can_submit
    assert not logfile_controller.submit_current_selection()
    compare_result(logfile_controller.generate_result(), paths, last_used_index=None)
    assert_called_set_can_submit(logfile_controller)

    # Missing logfile
    logfile_controller.select_logfile(3)
    assert not logfile_controller.can_submit
    assert not logfile_controller.submit_current_selection()
    compare_result(logfile_controller.generate_result(), paths, last_used_index=None)
    assert_didnt_call_set_can_submit(logfile_controller)

    logfile_controller.select_logfile(1)
    assert logfile_controller.can_submit
    assert logfile_controller.submit_current_selection()
    compare_result(logfile_controller.generate_result(), paths, last_used_index=1)
    assert_called_set_can_submit(logfile_controller)

    assert_didnt_call_update_logfile_list(logfile_controller)


def test_submit_path() -> None:
    logfile_controller = create_logfile_controller()
    logfile_controller.submit_path(DEFAULT_ACTIVE_LOGFILES[0].path)

    compare_result(
        logfile_controller.generate_result(), DEFAULT_PATHS, last_used_index=0
    )


def test_submit_path_new() -> None:
    logfile_controller = create_logfile_controller()
    submitted_path = Path("new_path")
    logfile_controller.submit_path(submitted_path)

    # The new submission is appended to the known logfiles
    compare_result(
        logfile_controller.generate_result(),
        DEFAULT_PATHS + (submitted_path,),
        last_used_index=len(DEFAULT_PATHS),
    )


def test_can_select_logfile_with_id() -> None:
    logfile_controller = create_logfile_controller()
    assert logfile_controller._can_select_logfile_with_id(0)
    assert not logfile_controller._can_select_logfile_with_id(1234)


def test_remove_logfile() -> None:
    logfile_controller = create_logfile_controller()

    # Invalid logfile
    logfile_controller.remove_logfile(1234)
    assert_didnt_call_set_can_submit(logfile_controller)
    assert_didnt_call_update_logfile_list(logfile_controller)

    # Remove an old logfile
    logfile_controller.remove_logfile(3)
    compare_result(
        logfile_controller.generate_result(), DEFAULT_PATHS[:-1], last_used_index=None
    )
    assert_didnt_call_set_can_submit(logfile_controller)
    assert_called_update_logfile_list(logfile_controller)

    # Remove the current selection
    logfile_controller.remove_logfile(0)
    compare_result(
        logfile_controller.generate_result(), DEFAULT_PATHS[1:-1], last_used_index=None
    )
    assert logfile_controller.selected_id is None
    assert_called_set_can_submit(logfile_controller)
    assert_called_update_logfile_list(logfile_controller)


def test_first_startup() -> None:
    # The program suggests some logfiles, but none is selected to start with
    logfile_controller = create_logfile_controller(last_used_id=None)

    # The user waits a bit, while their game is running in the background
    for i in range(5):
        assert not call_refresh_state(logfile_controller, updated_logfiles={0})

    # The user clicks to select their logfile
    logfile_controller.select_logfile(0)

    assert logfile_controller.submit_current_selection()
    compare_result(
        logfile_controller.generate_result(), DEFAULT_PATHS, last_used_index=0
    )


def test_startup_with_autoselect() -> None:
    logfile_controller = create_logfile_controller()

    # The user waits for their game to start
    for i in range(5):
        assert not call_refresh_state(logfile_controller)
        compare_result(
            logfile_controller.generate_result(), DEFAULT_PATHS, last_used_index=None
        )

    # The game starts
    assert call_refresh_state(logfile_controller, updated_logfiles={0})

    compare_result(
        logfile_controller.generate_result(), DEFAULT_PATHS, last_used_index=0
    )