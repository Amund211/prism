import time
from collections.abc import Iterable
from pathlib import Path

from prism.overlay.controller import OverlayController, RealOverlayController
from prism.overlay.file_utils import watch_file_with_reopen
from prism.overlay.nick_database import NickDatabase
from prism.overlay.output.overlay.run_overlay import run_overlay
from prism.overlay.output.printing import print_stats_table
from prism.overlay.player import Player
from prism.overlay.process_event import fast_forward_state
from prism.overlay.settings import Settings
from prism.overlay.state import OverlayState
from prism.overlay.threading import prepare_overlay

CLEAR_BETWEEN_DRAWS = True


def process_loglines_to_stdout(
    controller: OverlayController, loglines: Iterable[str]
) -> None:  # pragma: nocover
    """Process the state changes for each logline and redraw the screen if neccessary"""
    get_stat_list = prepare_overlay(controller, loglines=loglines)

    while True:
        time.sleep(0.1)

        sorted_stats = get_stat_list()

        if sorted_stats is None:
            continue

        # Store a persistent view to the current state
        state = controller.state

        print_stats_table(
            sorted_stats=sorted_stats,
            party_members=state.party_members,
            column_order=controller.settings.column_order,
            rating_configs=controller.settings.rating_configs,
            out_of_sync=state.out_of_sync,
            clear_between_draws=CLEAR_BETWEEN_DRAWS,
        )


def process_loglines_to_overlay(
    controller: OverlayController, loglines: Iterable[str], output_to_console: bool
) -> None:  # pragma: nocover
    """Process the state changes for each logline and output to an overlay"""
    get_stat_list = prepare_overlay(controller, loglines=loglines)

    if output_to_console:
        # Output to console every time we get a new stats list
        original_get_stat_list = get_stat_list

        def get_stat_list() -> list[Player] | None:
            sorted_stats = original_get_stat_list()

            if sorted_stats is not None:
                # Store a persistent view to the current state
                state = controller.state

                print_stats_table(
                    sorted_stats=sorted_stats,
                    party_members=state.party_members,
                    column_order=controller.settings.column_order,
                    rating_configs=controller.settings.rating_configs,
                    out_of_sync=state.out_of_sync,
                    clear_between_draws=CLEAR_BETWEEN_DRAWS,
                )

            return sorted_stats

    run_overlay(controller, get_stat_list)


def watch_from_logfile(
    logpath: Path,
    overlay: bool,
    console: bool,
    settings: Settings,
    nick_database: NickDatabase,
) -> None:  # pragma: nocover
    """Use the overlay on an active logfile"""

    assert overlay or console, "Need at least one output"

    state = OverlayState()

    controller = RealOverlayController(
        state=state,
        settings=settings,
        nick_database=nick_database,
    )

    with logpath.open("r", encoding="utf8", errors="replace") as logfile:
        # Process the entire logfile to get current player as well as potential
        # current party/lobby
        fast_forward_state(controller, logfile.readlines())
        final_position = logfile.tell()

    loglines = watch_file_with_reopen(logpath, start_at=final_position, blocking=True)

    # Process the rest of the loglines as they come in
    if not overlay:
        process_loglines_to_stdout(controller, loglines=loglines)
    else:
        process_loglines_to_overlay(
            controller,
            loglines=loglines,
            output_to_console=console,
        )
