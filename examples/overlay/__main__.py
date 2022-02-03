"""
Parse the chat on Hypixel to detect players in your party and bedwars lobby

Run from the root dir by `python -m examples.overlay [--logfile <path-to-logfile>]`
"""

import logging
import sys
import time
from datetime import date
from functools import partial
from itertools import count
from pathlib import Path
from typing import Iterable, Optional

from appdirs import AppDirs
from tendo import singleton  # type: ignore

from examples.overlay.antisniper_api import AntiSniperAPIKeyHolder
from examples.overlay.commandline import get_options
from examples.overlay.nick_database import EMPTY_DATABASE, NickDatabase
from examples.overlay.output.overlay import run_overlay
from examples.overlay.output.printing import print_stats_table
from examples.overlay.settings import Settings, get_settings
from examples.overlay.state import OverlayState, fast_forward_state
from examples.overlay.stats import Stats, clear_cache, uncache_stats
from examples.overlay.threading import prepare_overlay
from examples.overlay.user_interaction import prompt_for_logfile_path, wait_for_api_key
from prism.minecraft import MojangAPIError, get_uuid
from prism.playerdata import HypixelAPIKeyHolder

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
DOWNLOAD_THREAD_COUNT = 15


def tail_file_with_reopen(path: Path, timeout: float = 30) -> Iterable[str]:
    """Iterate over new lines in a file, reopen the file when stale"""
    reading_fresh_file = False
    while True:
        last_read = time.monotonic()
        with path.open("r", encoding="utf8", errors="replace") as f:
            # If we opened a new file, read it from the start
            if not reading_fresh_file:
                f.seek(0, 2)

            while True:
                line = f.readline()
                if not line:
                    # No new lines -> wait
                    if time.monotonic() - last_read > timeout:
                        # More than `timeout` seconds since last read -> reopen file
                        logger.debug("Timed out reading file '{f.name}'; reopening")
                        reading_fresh_file = True
                        break

                    time.sleep(0.1)
                    continue

                last_read = time.monotonic()
                yield line


def process_loglines_to_stdout(
    state: OverlayState,
    hypixel_key_holder: HypixelAPIKeyHolder,
    antisniper_key_holder: Optional[AntiSniperAPIKeyHolder],
    nick_database: NickDatabase,
    loglines: Iterable[str],
    thread_count: int = DOWNLOAD_THREAD_COUNT,
) -> None:
    """Process the state changes for each logline and redraw the screen if neccessary"""
    get_stat_list = prepare_overlay(
        state,
        hypixel_key_holder=hypixel_key_holder,
        antisniper_key_holder=antisniper_key_holder,
        nick_database=nick_database,
        loglines=loglines,
        thread_count=thread_count,
    )

    while True:
        time.sleep(0.1)

        sorted_stats = get_stat_list()

        if sorted_stats is None:
            continue

        with state.mutex:
            party_members = state.party_members.copy()
            out_of_sync = state.out_of_sync

        print_stats_table(
            sorted_stats=sorted_stats,
            party_members=party_members,
            out_of_sync=out_of_sync,
            clear_between_draws=CLEAR_BETWEEN_DRAWS,
        )


def process_loglines_to_overlay(
    state: OverlayState,
    hypixel_key_holder: HypixelAPIKeyHolder,
    antisniper_key_holder: Optional[AntiSniperAPIKeyHolder],
    nick_database: NickDatabase,
    loglines: Iterable[str],
    output_to_console: bool,
    thread_count: int = DOWNLOAD_THREAD_COUNT,
) -> None:
    """Process the state changes for each logline and output to an overlay"""
    get_stat_list = prepare_overlay(
        state,
        hypixel_key_holder=hypixel_key_holder,
        nick_database=nick_database,
        loglines=loglines,
        thread_count=thread_count,
        antisniper_key_holder=antisniper_key_holder,
    )

    if output_to_console:
        # Output to console every time we get a new stats list
        original_get_stat_list = get_stat_list

        def get_stat_list() -> Optional[list[Stats]]:
            sorted_stats = original_get_stat_list()

            if sorted_stats is not None:
                with state.mutex:
                    party_members = state.party_members.copy()
                    out_of_sync = state.out_of_sync

                print_stats_table(
                    sorted_stats=sorted_stats,
                    party_members=party_members,
                    out_of_sync=out_of_sync,
                    clear_between_draws=CLEAR_BETWEEN_DRAWS,
                )

            return sorted_stats

    run_overlay(state, get_stat_list)


def watch_from_logfile(
    logpath_string: str,
    overlay: bool,
    console: bool,
    settings: Settings,
    nick_database: NickDatabase,
) -> None:
    """Use the overlay on an active logfile"""

    assert overlay or console, "Need at least one output"

    hypixel_key_holder = HypixelAPIKeyHolder(settings.hypixel_api_key)

    if settings.use_antisniper_api and settings.antisniper_api_key is not None:
        antisniper_key_holder = AntiSniperAPIKeyHolder(settings.antisniper_api_key)
    else:
        antisniper_key_holder = None

    def set_nickname(username: str, nick: str) -> None:
        """Update the user's nickname"""
        try:
            own_uuid = get_uuid(username)
        except MojangAPIError as e:
            logger.error(
                f"Failed getting uuid for '{username}' when setting nickname. " f"'{e}'"
            )
            return

        if own_uuid is None:
            logger.error(
                f"Failed getting uuid for '{username}' when setting nickname. "
                "No match found."
            )
            return

        old_nick = None

        with settings.mutex:
            # Search the known nicks in settings for your own uuid
            for old_nick, nick_value in settings.known_nicks.items():
                if own_uuid == nick_value["uuid"]:
                    new_nick_value = nick_value
                    break
            else:
                # Found no matching entries - make a new one
                new_nick_value = {"uuid": own_uuid, "comment": username}
                old_nick = None

            # Remove your old nick if found
            if old_nick is not None:
                del settings.known_nicks[old_nick]

            # Add your new nick
            settings.known_nicks[nick] = new_nick_value
            settings.flush_to_disk()

        with nick_database.mutex:
            # Add your new nick
            nick_database.default_database[nick] = own_uuid

            # Delete your old nick if found
            if old_nick is not None:
                nick_database.default_database.pop(old_nick, None)

        if old_nick is not None:
            # Drop the stats cache for your old nick
            uncache_stats(old_nick)

        # Drop the stats cache for your new nick so that we can fetch the stats
        uncache_stats(nick)

    def set_api_key(new_key: str) -> None:
        """Update the API key that the download threads use"""
        hypixel_key_holder.key = new_key
        with settings.mutex:
            settings.hypixel_api_key = new_key
            settings.flush_to_disk()

        # Clear the stats cache in case the old api key was invalid
        clear_cache()

    state = OverlayState(
        lobby_players=set(),
        party_members=set(),
        set_api_key=set_api_key,
        set_nickname=set_nickname,
    )

    logpath = Path(logpath_string)

    with logpath.open("r", encoding="utf8", errors="replace") as logfile:
        # Process the entire logfile to get current player as well as potential
        # current party/lobby
        fast_forward_state(state, logfile.readlines())

    loglines = tail_file_with_reopen(logpath)

    # Process the rest of the loglines as they come in
    if not overlay:
        process_loglines_to_stdout(
            state,
            hypixel_key_holder=hypixel_key_holder,
            antisniper_key_holder=antisniper_key_holder,
            nick_database=nick_database,
            loglines=loglines,
        )
    else:
        process_loglines_to_overlay(
            state,
            hypixel_key_holder=hypixel_key_holder,
            antisniper_key_holder=antisniper_key_holder,
            nick_database=nick_database,
            loglines=loglines,
            output_to_console=console,
        )


def setup(loglevel: int = logging.WARNING) -> None:
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
        logpath = LOGDIR / f"{datestring}.{i}.log"
        if not logpath.exists():
            break

    logging.basicConfig(
        filename=logpath,
        level=loglevel,
        format="%(asctime)s;%(levelname)-8s;%(name)-30s;%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def test() -> None:
    """Test the implementation on a static logfile"""
    global TESTING, CLEAR_BETWEEN_DRAWS

    setup(logging.DEBUG)

    TESTING = True
    CLEAR_BETWEEN_DRAWS = False

    assert len(sys.argv) >= 3
    output = "overlay" if len(sys.argv) >= 4 and sys.argv[3] == "overlay" else "stdout"

    state = OverlayState(
        lobby_players=set(),
        party_members=set(),
        set_api_key=lambda x: None,
        set_nickname=lambda username, nick: None,
    )
    hypixel_key_holder = HypixelAPIKeyHolder("")
    antisniper_key_holder = None
    nick_database = EMPTY_DATABASE

    with open(sys.argv[2], "r", encoding="utf8", errors="replace") as logfile:
        loglines = logfile
        if output == "overlay":
            from itertools import chain, islice, repeat

            loglines_with_pause = chain(islice(repeat(""), 500), loglines, repeat(""))
            process_loglines_to_overlay(
                state,
                hypixel_key_holder=hypixel_key_holder,
                antisniper_key_holder=antisniper_key_holder,
                nick_database=nick_database,
                loglines=loglines_with_pause,
                output_to_console=True,
            )
        else:
            process_loglines_to_stdout(
                state,
                hypixel_key_holder=hypixel_key_holder,
                antisniper_key_holder=antisniper_key_holder,
                nick_database=nick_database,
                loglines=loglines,
            )


def main(*nick_databases: Path) -> None:
    """Run the overlay"""
    setup()

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
    )


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        test()
    else:
        main()
