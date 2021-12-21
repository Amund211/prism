"""
Search for /who responses in the logfile and print the found users' stats

Run from the examples dir by `python -m sidelay <path-to-logfile>`

Example string printed to logfile when typing /who:
'[Info: 2021-10-29 15:29:33.059151572: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] ONLINE: The_TOXIC__, T_T0xic, maskaom, NomexxD, Killerluise, Fruce_, 3Bitek, OhCradle, DanceMonky, Sweeetnesss, jbzn, squashypeas, Skydeaf, serocore'  # noqa: E501
"""

import logging
import sys
import time
from pathlib import Path
from typing import Iterable, Literal, Optional, TextIO

from examples.sidelay.output.overlay import stats_to_row
from examples.sidelay.output.overlay_window import CellValue, OverlayRow, OverlayWindow
from examples.sidelay.output.printing import print_stats_table
from examples.sidelay.parsing import parse_logline
from examples.sidelay.state import OverlayState, update_state
from examples.sidelay.stats import (
    NickedPlayer,
    Stats,
    get_bedwars_stats,
    rate_stats_for_non_party_members,
)
from hystatutils.utils import read_key

logging.basicConfig()
logger = logging.getLogger()

api_key = read_key(Path(sys.path[0]) / "api_key")

TESTING = False
CLEAR_BETWEEN_DRAWS = True


def tail_file(f: TextIO) -> Iterable[str]:
    """Iterate over new lines in a file"""
    f.seek(0, 2)
    while True:
        line = f.readline()
        if not line:
            # No new lines -> wait
            time.sleep(0.01)
            continue

        yield line


def get_sorted_stats(state: OverlayState) -> list[Stats]:
    stats: list[Stats]
    if TESTING:
        # No api requests in testing
        stats = [NickedPlayer(username=player) for player in state.lobby_players]
    else:
        stats = [
            get_bedwars_stats(player, api_key=api_key) for player in state.lobby_players
        ]

    return list(
        sorted(
            stats,
            key=rate_stats_for_non_party_members(state.party_members),
            reverse=True,
        )
    )


def fast_forward_state(state: OverlayState, loglines: Iterable[str]) -> None:
    """Process the state changes for each logline without outputting anything"""
    for line in loglines:
        event = parse_logline(line)

        if event is None:
            continue

        update_state(state, event)


def process_loglines_to_stdout(state: OverlayState, loglines: Iterable[str]) -> None:
    """Process the state changes for each logline and redraw the screen if neccessary"""
    for line in loglines:
        event = parse_logline(line)

        if event is None:
            continue

        redraw = update_state(state, event)

        if redraw:
            logger.info(f"Party = {', '.join(state.party_members)}")
            logger.info(f"Lobby = {', '.join(state.lobby_players)}")

            sorted_stats = get_sorted_stats(state)

            print_stats_table(
                sorted_stats=sorted_stats,
                party_members=state.party_members,
                out_of_sync=state.out_of_sync,
                clear_between_draws=CLEAR_BETWEEN_DRAWS,
            )


def process_loglines_to_overlay(state: OverlayState, loglines: Iterable[str]) -> None:
    COLUMNS = ("username", "stars", "fkdr", "winstreak")
    PRETTY_COLUMN_NAMES = {
        "username": "IGN",
        "stars": "Stars",
        "fkdr": "FKDR",
        "winstreak": "WS",
    }

    loglines_iterator = iter(loglines)

    def get_new_rows() -> Optional[list[OverlayRow]]:
        try:
            logline = next(loglines_iterator)
        except StopIteration:
            sys.exit(0)

        event = parse_logline(logline)

        if event is None:
            return None

        redraw = update_state(state, event)
        if not redraw:
            return None

        sorted_stats = get_sorted_stats(state)

        return [stats_to_row(stats) for stats in sorted_stats]

    def get_new_data() -> tuple[bool, Optional[CellValue], Optional[list[OverlayRow]]]:
        new_rows = get_new_rows()
        return (
            state.in_queue,
            CellValue("Overlay out of sync. Use /who", "red")
            if state.out_of_sync
            else None,
            new_rows,
        )

    def set_not_in_queue() -> None:
        state.in_queue = False

    overlay = OverlayWindow(
        column_names=list(COLUMNS),
        pretty_column_names=PRETTY_COLUMN_NAMES,
        left_justified_columns={0},
        close_callback=lambda: sys.exit(0),
        minimize_callback=set_not_in_queue,
        get_new_data=get_new_data,
    )
    overlay.run()


def watch_from_logfile(logpath: str, output: Literal["stdout", "overlay"]) -> None:
    """Use the overlay on an active logfile"""
    state = OverlayState(lobby_players=set(), party_members=set())

    with open(logpath, "r") as logfile:
        # Process the entire logfile to get current player as well as potential
        # current party
        old_loglines = logfile.readlines()
        fast_forward_state(state, old_loglines)

        # Process the rest of the loglines as they come in
        loglines = tail_file(logfile)
        if output == "stdout":
            process_loglines_to_stdout(state, loglines)
        else:
            process_loglines_to_overlay(state, loglines)


def test() -> None:
    """Test the implementation on a static logfile"""
    global TESTING, CLEAR_BETWEEN_DRAWS

    TESTING = True
    CLEAR_BETWEEN_DRAWS = False

    logger.setLevel(logging.DEBUG)

    assert len(sys.argv) >= 3
    output = "overlay" if len(sys.argv) >= 4 and sys.argv[3] == "overlay" else "stdout"

    state = OverlayState(lobby_players=set(), party_members=set())

    with open(sys.argv[2], "r") as logfile:
        loglines = logfile
        if output == "overlay":
            from itertools import chain, islice, repeat

            loglines_with_pause = chain(islice(repeat(""), 500), loglines, repeat(""))
            process_loglines_to_overlay(state, loglines_with_pause)
        else:
            process_loglines_to_stdout(state, loglines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Must provide a path to the logfile!", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "test":
        test()
    else:
        watch_from_logfile(sys.argv[1], "overlay")
