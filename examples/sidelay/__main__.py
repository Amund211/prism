"""
Search for /who responses in the logfile and print the found users' stats

Run from the examples dir by `python -m sidelay <path-to-logfile>`

Example string printed to logfile when typing /who:
'[Info: 2021-10-29 15:29:33.059151572: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] ONLINE: The_TOXIC__, T_T0xic, maskaom, NomexxD, Killerluise, Fruce_, 3Bitek, OhCradle, DanceMonky, Sweeetnesss, jbzn, squashypeas, Skydeaf, serocore'  # noqa: E501
"""

import logging
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Literal, Optional, TextIO

from examples.sidelay.output.overlay import run_overlay
from examples.sidelay.output.printing import print_stats_table
from examples.sidelay.parsing import parse_logline
from examples.sidelay.state import OverlayState, update_state
from examples.sidelay.stats import (
    Stats,
    get_bedwars_stats,
    get_cached_stats,
    set_player_pending,
    sort_stats,
)
from hystatutils.playerdata import HypixelAPIKeyHolder
from hystatutils.utils import read_key

logging.basicConfig()
logger = logging.getLogger()

api_key = read_key(Path(sys.path[0]) / "api_key")
key_holder = HypixelAPIKeyHolder(api_key)

TESTING = False
CLEAR_BETWEEN_DRAWS = True
DOWNLOAD_THREAD_COUNT = 15


class UpdateStateThread(threading.Thread):
    """Thread that reads from the logfile and updates the state"""

    def __init__(
        self,
        state: OverlayState,
        loglines: Iterable[str],
        redraw_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.state = state
        self.loglines = loglines
        self.redraw_event = redraw_event

    def run(self) -> None:
        """Read self.loglines and update self.state"""
        try:
            for line in self.loglines:
                event = parse_logline(line)

                if event is None:
                    continue

                with self.state.mutex:
                    redraw = update_state(self.state, event)
                    if redraw:
                        # Tell the main thread we need a redraw
                        self.redraw_event.set()
        except (OSError, ValueError) as e:
            # Catch 'read on closed file' if the main thread exited
            logger.debug(f"Exception caught in state update tread: {e}. Exiting")
            return


class GetStatsThread(threading.Thread):
    """Thread that downloads and stores players' stats to cache"""

    def __init__(
        self,
        requests_queue: queue.Queue[str],
        completed_queue: queue.Queue[str],
        key_holder: HypixelAPIKeyHolder,
    ) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.requests_queue = requests_queue
        self.completed_queue = completed_queue
        self.key_holder = key_holder

    def run(self) -> None:
        """Get requested stats from the queue and download them"""
        while True:
            username = self.requests_queue.get()

            # get_bedwars_stats sets the stats cache which will be read from later
            get_bedwars_stats(username, key_holder=self.key_holder)
            self.requests_queue.task_done()

            # Tell the main thread that we downloaded this user's stats
            self.completed_queue.put(username)


def tail_file(f: TextIO) -> Iterable[str]:
    """Iterate over new lines in a file"""
    f.seek(0, 2)
    while True:
        line = f.readline()
        if not line:
            # No new lines -> wait
            time.sleep(0.1)
            continue

        yield line


def fast_forward_state(state: OverlayState, loglines: Iterable[str]) -> None:
    """Process the state changes for each logline without outputting anything"""
    for line in loglines:
        event = parse_logline(line)

        if event is None:
            continue

        update_state(state, event)


def should_redraw(
    state: OverlayState,
    redraw_event: threading.Event,
    completed_stats_queue: queue.Queue[str],
) -> bool:
    """Check if any updates happened since last time that needs a redraw"""
    # Check the work done by the state update and stats download threads
    redraw = False

    # Check if the state update thread has issued any redraws since last time
    with state.mutex:
        if redraw_event.is_set():
            redraw = True
            redraw_event.clear()

    # Check if any of the stats downloaded since last render are still in the lobby
    while True:
        try:
            username = completed_stats_queue.get_nowait()
        except queue.Empty:
            break
        else:
            completed_stats_queue.task_done()
            with state.mutex:
                if username in state.lobby_players:
                    # We just received the stats of a player in the lobby
                    # Redraw the screen in case the stats weren't there last time
                    redraw = True

    return redraw


def prepare_overlay(
    state: OverlayState, loglines: Iterable[str], thread_count: int
) -> Callable[[], Optional[list[Stats]]]:
    """
    Set up and return get_stat_list

    get_stat_list returns an updated list of stats of the players in the lobby,
    or None if no updates happened since last call.

    This function spawns threads that perform the state updates and stats downloading
    """

    # Usernames we want the stats of
    requested_stats_queue = queue.Queue[str]()
    # Usernames we have newly downloaded the stats of
    completed_stats_queue = queue.Queue[str]()
    # Redraw requests from state updates
    redraw_event = threading.Event()

    # Spawn thread for updating state
    UpdateStateThread(state=state, loglines=loglines, redraw_event=redraw_event).start()

    # Spawn threads for downloading stats
    for i in range(thread_count):
        GetStatsThread(
            requests_queue=requested_stats_queue,
            completed_queue=completed_stats_queue,
            key_holder=key_holder,
        ).start()

    def get_stat_list() -> Optional[list[Stats]]:
        """
        Get an updated list of stats of the players in the lobby. None if no updates
        """

        redraw = should_redraw(
            state,
            redraw_event=redraw_event,
            completed_stats_queue=completed_stats_queue,
        )

        if not redraw:
            return None

        # Get the cached stats for the players in the lobby
        stats: list[Stats] = []

        with state.mutex:
            for player in state.lobby_players:
                cached_stats = get_cached_stats(player)
                if cached_stats is None:
                    # No query made for this player yet
                    # Start a query and note that a query has been started
                    cached_stats = set_player_pending(player)
                    requested_stats_queue.put(player)
                stats.append(cached_stats)

            sorted_stats = sort_stats(stats, state.party_members)

            return sorted_stats

    return get_stat_list


def process_loglines_to_stdout(
    state: OverlayState,
    loglines: Iterable[str],
    thread_count: int = DOWNLOAD_THREAD_COUNT,
) -> None:
    """Process the state changes for each logline and redraw the screen if neccessary"""
    get_stat_list = prepare_overlay(state, loglines, thread_count=thread_count)

    while True:
        time.sleep(0.1)

        sorted_stats = get_stat_list()

        if sorted_stats is None:
            continue

        with state.mutex:
            print_stats_table(
                sorted_stats=sorted_stats,
                party_members=state.party_members,
                out_of_sync=state.out_of_sync,
                clear_between_draws=CLEAR_BETWEEN_DRAWS,
            )


def process_loglines_to_overlay(
    state: OverlayState,
    loglines: Iterable[str],
    output_to_console: bool,
    thread_count: int = DOWNLOAD_THREAD_COUNT,
) -> None:
    """Process the state changes for each logline and output to an overlay"""
    get_stat_list = prepare_overlay(state, loglines, thread_count)

    if output_to_console:
        # Output to console every time we get a new stats list
        original_get_stat_list = get_stat_list

        def get_stat_list() -> Optional[list[Stats]]:
            sorted_stats = original_get_stat_list()

            if sorted_stats is not None:
                with state.mutex:
                    print_stats_table(
                        sorted_stats=sorted_stats,
                        party_members=state.party_members,
                        out_of_sync=state.out_of_sync,
                        clear_between_draws=CLEAR_BETWEEN_DRAWS,
                    )

            return sorted_stats

    run_overlay(state, get_stat_list)


def watch_from_logfile(logpath: str, output: Literal["stdout", "overlay"]) -> None:
    """Use the overlay on an active logfile"""
    state = OverlayState(lobby_players=set(), party_members=set())

    with open(logpath, "r", encoding="utf8") as logfile:
        # Process the entire logfile to get current player as well as potential
        # current party/lobby
        old_loglines = logfile.readlines()
        fast_forward_state(state, old_loglines)

        loglines = tail_file(logfile)

        # Process the rest of the loglines as they come in
        if output == "stdout":
            process_loglines_to_stdout(state, loglines)
        else:
            process_loglines_to_overlay(state, loglines, output_to_console=True)


def test() -> None:
    """Test the implementation on a static logfile"""
    global TESTING, CLEAR_BETWEEN_DRAWS

    TESTING = True
    CLEAR_BETWEEN_DRAWS = False

    logger.setLevel(logging.DEBUG)

    assert len(sys.argv) >= 3
    output = "overlay" if len(sys.argv) >= 4 and sys.argv[3] == "overlay" else "stdout"

    state = OverlayState(lobby_players=set(), party_members=set())

    with open(sys.argv[2], "r", encoding="utf8") as logfile:
        loglines = logfile
        if output == "overlay":
            from itertools import chain, islice, repeat

            loglines_with_pause = chain(islice(repeat(""), 500), loglines, repeat(""))
            process_loglines_to_overlay(
                state, loglines_with_pause, output_to_console=True
            )
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
