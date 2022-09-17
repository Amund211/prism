"""
Parse the chat on Hypixel to detect players in your party and bedwars lobby

Run from the root dir by `python -m examples.overlay [--logfile <path-to-logfile>]`
"""

import functools
import logging
import platform
import sys
import time
from collections.abc import Iterable
from datetime import date, datetime
from itertools import count
from pathlib import Path

from appdirs import AppDirs
from tendo import singleton  # type: ignore

from examples.overlay import VERSION_STRING
from examples.overlay.behaviour import fast_forward_state
from examples.overlay.commandline import get_options
from examples.overlay.controller import OverlayController, RealOverlayController
from examples.overlay.file_utils import watch_file_with_reopen
from examples.overlay.nick_database import NickDatabase
from examples.overlay.output.overlay.run_overlay import run_overlay
from examples.overlay.output.printing import print_stats_table
from examples.overlay.player import Player
from examples.overlay.settings import Settings, get_settings
from examples.overlay.state import OverlayState
from examples.overlay.threading import prepare_overlay
from examples.overlay.user_interaction import prompt_for_logfile_path, wait_for_api_key

# Variable that stores our singleinstance lock so that it doesn't go out of scope
# and get released
SINGLEINSTANCE_LOCK = None

dirs = AppDirs(appname="prism_overlay")

CONFIG_DIR = Path(dirs.user_config_dir)
DEFAULT_SETTINGS_PATH = CONFIG_DIR / "settings.toml"
DEFAULT_LOGFILE_CACHE_PATH = CONFIG_DIR / "known_logfiles.toml"

CACHE_DIR = Path(dirs.user_cache_dir)


LOGDIR = Path(dirs.user_log_dir)

logger = logging.getLogger(__name__)

TESTING = False
CLEAR_BETWEEN_DRAWS = True


def slow_iterable(iterable: Iterable[str], wait: float = 1) -> Iterable[str]:
    """Wait `wait` seconds between each yield from iterable"""
    # Used for testing
    for item in iterable:
        time.sleep(wait)
        print(f"Yielding '{item}'")
        yield item
    print("Done yielding")


def process_loglines_to_stdout(
    controller: OverlayController,
    loglines: Iterable[str],
    thread_count: int,
) -> None:
    """Process the state changes for each logline and redraw the screen if neccessary"""
    get_stat_list = prepare_overlay(
        controller, loglines=loglines, thread_count=thread_count
    )

    while True:
        time.sleep(0.1)

        sorted_stats = get_stat_list()

        if sorted_stats is None:
            continue

        with controller.state.mutex:
            party_members = controller.state.party_members.copy()
            out_of_sync = controller.state.out_of_sync

        print_stats_table(
            sorted_stats=sorted_stats,
            party_members=party_members,
            out_of_sync=out_of_sync,
            clear_between_draws=CLEAR_BETWEEN_DRAWS,
        )


def process_loglines_to_overlay(
    controller: OverlayController,
    loglines: Iterable[str],
    output_to_console: bool,
    thread_count: int,
) -> None:
    """Process the state changes for each logline and output to an overlay"""
    get_stat_list = prepare_overlay(
        controller, loglines=loglines, thread_count=thread_count
    )

    if output_to_console:
        # Output to console every time we get a new stats list
        original_get_stat_list = get_stat_list

        def get_stat_list() -> list[Player] | None:
            sorted_stats = original_get_stat_list()

            if sorted_stats is not None:
                with controller.state.mutex:
                    party_members = controller.state.party_members.copy()
                    out_of_sync = controller.state.out_of_sync

                print_stats_table(
                    sorted_stats=sorted_stats,
                    party_members=party_members,
                    out_of_sync=out_of_sync,
                    clear_between_draws=CLEAR_BETWEEN_DRAWS,
                )

            return sorted_stats

    run_overlay(controller, get_stat_list)


def watch_from_logfile(
    logpath_string: str,
    overlay: bool,
    console: bool,
    settings: Settings,
    nick_database: NickDatabase,
    thread_count: int,
) -> None:
    """Use the overlay on an active logfile"""

    assert overlay or console, "Need at least one output"

    state = OverlayState(lobby_players=set(), party_members=set())

    controller = RealOverlayController(
        state=state,
        settings=settings,
        nick_database=nick_database,
    )

    logpath = Path(logpath_string)

    with logpath.open("r", encoding="utf8", errors="replace") as logfile:
        # Process the entire logfile to get current player as well as potential
        # current party/lobby
        fast_forward_state(controller, logfile.readlines())
        final_position = logfile.tell()

    loglines = watch_file_with_reopen(
        logpath, start_at=final_position, reopen_timeout=30, poll_timeout=0.1
    )

    # Process the rest of the loglines as they come in
    if not overlay:
        process_loglines_to_stdout(
            controller, loglines=loglines, thread_count=thread_count
        )
    else:
        process_loglines_to_overlay(
            controller,
            loglines=loglines,
            output_to_console=console,
            thread_count=thread_count,
        )


def setup(loglevel: int = logging.WARNING, log_prefix: str = "") -> None:
    """Set up directory structure and logging"""
    # Rename old directories
    olddirs = AppDirs(appname="hystatutils_overlay")
    for dirname in [
        "user_data_dir",
        "user_config_dir",
        "user_cache_dir",
        "site_data_dir",
        "site_config_dir",
        "user_log_dir",
    ]:
        olddir = Path(getattr(olddirs, dirname))
        newdir = Path(getattr(dirs, dirname))
        if olddir.is_dir() and not newdir.is_dir():
            newdir.parent.mkdir(parents=True, exist_ok=True)
            olddir.rename(newdir)
    ########################

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Only allow one instance of the overlay
    global SINGLEINSTANCE_LOCK
    try:
        SINGLEINSTANCE_LOCK = singleton.SingleInstance(
            lockfile=str(CACHE_DIR / "prism_overlay.lock")
        )
    except singleton.SingleInstanceException:
        # TODO: Shown the running overlay window
        print(
            "You can only run one instance of the overlay at the time", file=sys.stderr
        )
        sys.exit(1)

    LOGDIR.mkdir(parents=True, exist_ok=True)

    datestring = date.today().isoformat()

    for i in count():
        logpath = LOGDIR / f"{log_prefix}{datestring}.{i}.log"
        if not logpath.exists():
            break

    logging.basicConfig(
        filename=logpath,
        level=loglevel,
        format="%(asctime)s;%(levelname)-8s;%(name)-30s;%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Log system+version info
    current_datestring = datetime.now().isoformat(timespec="seconds")
    logger.setLevel(logging.DEBUG)
    logger.debug(f"Starting prism overlay {VERSION_STRING} at {current_datestring}")
    logger.debug(f"Running on {platform.uname()}. Python {platform.python_version()}")
    logger.setLevel(loglevel)


def test() -> None:
    """Test the implementation on a static logfile or a list of loglines"""
    options = get_options(
        args=sys.argv[2:], default_settings_path=DEFAULT_SETTINGS_PATH
    )

    setup(logging.DEBUG, log_prefix="test_")

    slow, wait = False, 1
    overlay = True
    console = options.output_to_console

    loglines: Iterable[str]
    if options.logfile_path is not None:
        loglines = options.logfile_path.open("r", encoding="utf8", errors="replace")
    else:
        CHAT = "(Client thread) Info [CHAT] "
        loglines = [
            "(Client thread) Info Setting user: You",
            f"{CHAT}You have joined [MVP++] Teammate's party!",
            f"{CHAT}You'll be partying with: Notch",
            f"{CHAT}Teammate has joined (2/16)!",  # out of sync
            f"{CHAT}You has joined (3/16)!",
            f"{CHAT}ONLINE: You, Teammate, Hypixel",  # in sync
            f"{CHAT}Technoblade has joined (4/16)!",
            f"{CHAT}Manhal_IQ_ has joined (5/16)!",
            f"{CHAT}edater has joined (6/16)!",  # denicked by api
            f"{CHAT}AmazingNickThatDoesntExist has joined (7/16)!",  # Nicked teammate
            # f"{CHAT}Protect your bed and destroy the enemy beds.",  # game start
            # f"{CHAT}               Bed Wars ",  # game end
            # f"{CHAT}1st Killer - [MVP+] Player1",  # game end
        ]

    if slow:
        loglines = slow_iterable(loglines, wait=wait)

    settings = get_settings(options.settings_path, lambda: "not-a-valid-api-key")

    with settings.mutex:
        default_database = {
            nick: value["uuid"] for nick, value in settings.known_nicks.items()
        }

    nick_database = NickDatabase.from_disk([], default_database=default_database)

    # watch_from_logfile
    state = OverlayState(lobby_players=set(), party_members=set())

    controller = RealOverlayController(
        state=state,
        settings=settings,
        nick_database=nick_database,
    )

    if not overlay:
        process_loglines_to_stdout(
            controller, loglines=loglines, thread_count=options.threads
        )
    else:
        process_loglines_to_overlay(
            controller,
            loglines=loglines,
            output_to_console=console,
            thread_count=options.threads,
        )


def main(*nick_databases: Path) -> None:
    """Run the overlay"""
    options = get_options(default_settings_path=DEFAULT_SETTINGS_PATH)

    setup(options.loglevel)

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed creating settings directory! '{e}'")
        sys.exit(1)

    if options.logfile_path is None:
        logfile_path = prompt_for_logfile_path(DEFAULT_LOGFILE_CACHE_PATH)
    else:
        logfile_path = options.logfile_path

    settings = get_settings(
        options.settings_path,
        functools.partial(wait_for_api_key, logfile_path, options.settings_path),
    )

    with settings.mutex:
        default_database = {
            nick: value["uuid"] for nick, value in settings.known_nicks.items()
        }

    nick_database = NickDatabase.from_disk(
        list(nick_databases), default_database=default_database
    )

    watch_from_logfile(
        str(logfile_path),
        overlay=True,
        console=options.output_to_console,
        settings=settings,
        nick_database=nick_database,
        thread_count=options.threads,
    )


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        test()
    else:
        main()
