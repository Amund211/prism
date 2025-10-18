from collections.abc import Iterable

from prism.overlay.commandline import Options
from prism.overlay.controller import OverlayController
from prism.overlay.directories import DEFAULT_LOGFILE_CACHE_PATH
from prism.overlay.file_utils import watch_file_with_reopen
from prism.overlay.output.overlay.run_overlay import run_overlay
from prism.overlay.process_event import fast_forward_state
from prism.overlay.settings import Settings
from prism.overlay.threading import prepare_overlay
from prism.overlay.user_interaction.get_logfile import prompt_for_logfile_path

CLEAR_BETWEEN_DRAWS = True


def prompt_and_read_logfile(
    controller: OverlayController, options: Options, settings: Settings
) -> Iterable[str]:  # pragma: nocover
    if options.logfile_path is None:
        logfile_path = prompt_for_logfile_path(
            DEFAULT_LOGFILE_CACHE_PATH, settings.autoselect_logfile
        )
    else:
        logfile_path = options.logfile_path

    with logfile_path.open("r", encoding="utf8", errors="replace") as logfile:
        # Process the entire logfile to get current player as well as potential
        # current party/lobby
        fast_forward_state(controller, logfile.readlines())
        final_position = logfile.tell()

    return watch_file_with_reopen(logfile_path, start_at=final_position, blocking=True)


def process_loglines_to_overlay(
    controller: OverlayController, loglines: Iterable[str]
) -> None:  # pragma: nocover
    """Process the state changes for each logline and output to an overlay"""
    get_stat_list = prepare_overlay(controller, loglines=loglines)

    run_overlay(controller, get_stat_list)
