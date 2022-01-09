"""
Parse the chat on Hypixel to detect players in your party and bedwars lobby

Run from the root dir by `python -m examples.sidelay [--logfile <path-to-logfile>]`
"""

import logging
import sys
import time
from functools import partial
from pathlib import Path
from typing import Iterable, Optional, TextIO

from appdirs import AppDirs

from examples.sidelay.commandline import get_options
from examples.sidelay.output.overlay import run_overlay
from examples.sidelay.output.printing import print_stats_table
from examples.sidelay.settings import Settings, get_settings
from examples.sidelay.state import OverlayState, fast_forward_state
from examples.sidelay.stats import Stats
from examples.sidelay.threading import prepare_overlay
from examples.sidelay.user_interaction import prompt_for_logfile_path, wait_for_api_key
from hystatutils.playerdata import HypixelAPIKeyHolder

dirs = AppDirs(appname="hystatutils_overlay")
CONFIG_DIR = Path(dirs.user_config_dir)
DEFAULT_SETTINGS_PATH = CONFIG_DIR / "settings.toml"
DEFAULT_LOGFILE_CACHE_PATH = CONFIG_DIR / "known_logfiles.toml"

logging.basicConfig()
logger = logging.getLogger()

TESTING = False
CLEAR_BETWEEN_DRAWS = True
DOWNLOAD_THREAD_COUNT = 15


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


def process_loglines_to_stdout(
    state: OverlayState,
    key_holder: HypixelAPIKeyHolder,
    loglines: Iterable[str],
    thread_count: int = DOWNLOAD_THREAD_COUNT,
) -> None:
    """Process the state changes for each logline and redraw the screen if neccessary"""
    get_stat_list = prepare_overlay(
        state, key_holder, loglines, thread_count=thread_count
    )

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
    key_holder: HypixelAPIKeyHolder,
    loglines: Iterable[str],
    output_to_console: bool,
    thread_count: int = DOWNLOAD_THREAD_COUNT,
) -> None:
    """Process the state changes for each logline and output to an overlay"""
    get_stat_list = prepare_overlay(state, key_holder, loglines, thread_count)

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


def watch_from_logfile(
    logpath: str, overlay: bool, console: bool, settings: Settings
) -> None:
    """Use the overlay on an active logfile"""

    assert overlay or console, "Need at least one output"

    key_holder = HypixelAPIKeyHolder(settings.hypixel_api_key)

    def set_api_key(new_key: str) -> None:
        """Update the API key that the download threads use"""
        # TODO: Potentially invalidate the entire/some parts of the stats cache
        key_holder.key = new_key
        settings.hypixel_api_key = new_key
        settings.flush_to_disk()

    state = OverlayState(
        lobby_players=set(), party_members=set(), set_api_key=set_api_key
    )

    with open(logpath, "r", encoding="utf8") as logfile:
        # Process the entire logfile to get current player as well as potential
        # current party/lobby
        fast_forward_state(state, logfile.readlines())

        loglines = tail_file(logfile)

        # Process the rest of the loglines as they come in
        if not overlay:
            process_loglines_to_stdout(state, key_holder, loglines)
        else:
            process_loglines_to_overlay(
                state, key_holder, loglines, output_to_console=console
            )


def test() -> None:
    """Test the implementation on a static logfile"""
    global TESTING, CLEAR_BETWEEN_DRAWS

    TESTING = True
    CLEAR_BETWEEN_DRAWS = False

    logger.setLevel(logging.DEBUG)

    assert len(sys.argv) >= 3
    output = "overlay" if len(sys.argv) >= 4 and sys.argv[3] == "overlay" else "stdout"

    state = OverlayState(
        lobby_players=set(), party_members=set(), set_api_key=lambda x: None
    )
    key_holder = HypixelAPIKeyHolder("")

    with open(sys.argv[2], "r", encoding="utf8") as logfile:
        loglines = logfile
        if output == "overlay":
            from itertools import chain, islice, repeat

            loglines_with_pause = chain(islice(repeat(""), 500), loglines, repeat(""))
            process_loglines_to_overlay(
                state, key_holder, loglines_with_pause, output_to_console=True
            )
        else:
            process_loglines_to_stdout(state, key_holder, loglines)


def main() -> None:
    """Run the overlay"""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Failed creating settings directory! '{e}'", file=sys.stderr)
        logger.error(f"Failed creating settings directory! '{e}'")
        sys.exit(1)
    options = get_options(default_settings_path=DEFAULT_SETTINGS_PATH)

    if options.logfile_path is None:
        logfile_path = prompt_for_logfile_path(DEFAULT_LOGFILE_CACHE_PATH)
    else:
        logfile_path = options.logfile_path

    settings = get_settings(
        options.settings_path,
        partial(wait_for_api_key, logfile_path, options.settings_path),
    )
    watch_from_logfile(
        str(logfile_path),
        overlay=True,
        console=options.output_to_console,
        settings=settings,
    )


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        test()
    else:
        main()
