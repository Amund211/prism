"""
Parse the chat on Hypixel to detect players in your party and bedwars lobby

Run from the root dir by `python -m examples.overlay [--logfile <path-to-logfile>]`
"""

import functools
import logging
import os
import sys
import time
from datetime import date
from itertools import count
from pathlib import Path
from typing import Callable, Iterable, Optional

from appdirs import AppDirs
from tendo import singleton  # type: ignore

import examples.overlay.antisniper_api as antisniper_api
from examples.overlay.antisniper_api import AntiSniperAPIKeyHolder
from examples.overlay.commandline import get_options
from examples.overlay.nick_database import NickDatabase
from examples.overlay.output.overlay import run_overlay
from examples.overlay.output.printing import print_stats_table
from examples.overlay.settings import Settings, api_key_is_valid, get_settings
from examples.overlay.state import OverlayState, fast_forward_state
from examples.overlay.stats import Player, clear_cache, uncache_stats
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


def slow_iterable(iterable: Iterable[str], wait: float = 1) -> Iterable[str]:
    """Wait `wait` seconds between each yield from iterable"""
    # Used for testing
    for item in iterable:
        time.sleep(wait)
        print(f"Yielding '{item}'")
        yield item
    print("Done yielding")


def tail_file_with_reopen(path: Path, timeout: float = 30) -> Iterable[str]:
    """Iterate over new lines in a file, reopen the file when stale"""
    # Seek to the end of the first file we open
    last_position = 0

    while True:
        last_read = time.monotonic()
        with path.open("r", encoding="utf8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            new_filesize = f.tell()

            if last_position > new_filesize:
                # File has been truncated - assume it is new and read from the start
                f.seek(0, os.SEEK_SET)
            else:
                # File is no smaller than at the last read, assume it is the same file
                # and seek to where we left off
                f.seek(last_position, os.SEEK_SET)

            while True:
                line = f.readline()
                last_position = f.tell()
                if not line:
                    # No new lines -> wait
                    if time.monotonic() - last_read > timeout:
                        # More than `timeout` seconds since last read -> reopen file
                        logger.debug(f"Timed out reading file '{path}'; reopening")
                        break

                    time.sleep(0.1)
                    continue

                last_read = time.monotonic()
                yield line


def process_loglines_to_stdout(
    state: OverlayState,
    hypixel_key_holder: HypixelAPIKeyHolder,
    antisniper_key_holder: AntiSniperAPIKeyHolder | None,
    denick: Callable[[str], Optional[str]],
    loglines: Iterable[str],
    thread_count: int = DOWNLOAD_THREAD_COUNT,
) -> None:
    """Process the state changes for each logline and redraw the screen if neccessary"""
    get_stat_list = prepare_overlay(
        state,
        hypixel_key_holder=hypixel_key_holder,
        antisniper_key_holder=antisniper_key_holder,
        denick=denick,
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
    antisniper_key_holder: AntiSniperAPIKeyHolder | None,
    denick: Callable[[str], Optional[str]],
    loglines: Iterable[str],
    output_to_console: bool,
    thread_count: int = DOWNLOAD_THREAD_COUNT,
) -> None:
    """Process the state changes for each logline and output to an overlay"""
    get_stat_list = prepare_overlay(
        state,
        hypixel_key_holder=hypixel_key_holder,
        antisniper_key_holder=antisniper_key_holder,
        denick=denick,
        loglines=loglines,
        thread_count=thread_count,
    )

    if output_to_console:
        # Output to console every time we get a new stats list
        original_get_stat_list = get_stat_list

        def get_stat_list() -> list[Player] | None:
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


def denick_with_api(
    nick: str,
    nick_database: NickDatabase,
    antisniper_key_holder: AntiSniperAPIKeyHolder,
) -> Optional[str]:
    """Try denicking via the antisniper API, fallback to dict"""
    uuid = nick_database.get_default(nick)

    # Return if the user has specified a denick
    if uuid is not None:
        logger.debug(f"Denicked with default database {nick} -> {uuid}")
        return uuid

    if antisniper_key_holder is not None:
        uuid = antisniper_api.denick(nick, key_holder=antisniper_key_holder)

        if uuid is not None:
            logger.debug(f"Denicked with api {nick} -> {uuid}")
            return uuid

    uuid = nick_database.get(nick)

    if uuid is not None:
        logger.debug(f"Denicked with database {nick} -> {uuid}")
        return uuid

    logger.debug(f"Failed denicking {nick}")

    return None


def set_nickname(
    username: str | None, nick: str, settings: Settings, nick_database: NickDatabase
) -> None:
    """Update the user's nickname"""
    logger.debug(f"Setting denick {nick=} => {username=}")

    old_nick = None

    if username is not None:
        try:
            uuid = get_uuid(username)
        except MojangAPIError as e:
            logger.error(f"API error when getting uuid for '{username}'. '{e}'")
            uuid = None

        if uuid is None:
            logger.error(f"Failed getting uuid for '{username}' when setting nickname.")
            # Delete the entry for this nick
            old_nick = nick
    else:
        uuid = None
        # Delete the entry for this nick
        old_nick = nick

    with settings.mutex:
        if uuid is not None and username is not None:
            # Search the known nicks in settings for the uuid
            for old_nick, nick_value in settings.known_nicks.items():
                if uuid == nick_value["uuid"]:
                    new_nick_value = nick_value
                    break
            else:
                # Found no matching entries - make a new one
                new_nick_value = {"uuid": uuid, "comment": username}
                old_nick = None
        else:
            new_nick_value = None

        # Remove the old nick if found
        if old_nick is not None:
            settings.known_nicks.pop(old_nick, None)

        if new_nick_value is not None:
            # Add your new nick
            settings.known_nicks[nick] = new_nick_value

        settings.flush_to_disk()

    with nick_database.mutex:
        # Delete your old nick if found
        if old_nick is not None:
            nick_database.default_database.pop(old_nick, None)

        if uuid is not None:
            # Add your new nick
            nick_database.default_database[nick] = uuid

    if old_nick is not None:
        # Drop the stats cache for your old nick
        uncache_stats(old_nick)

    # Drop the stats cache for your new nick so that we can fetch the stats
    uncache_stats(nick)


def set_api_key(
    new_key: str, settings: Settings, hypixel_key_holder: HypixelAPIKeyHolder
) -> None:
    """Update the API key that the download threads use"""
    hypixel_key_holder.key = new_key
    with settings.mutex:
        settings.hypixel_api_key = new_key
        settings.flush_to_disk()

    # Clear the stats cache in case the old api key was invalid
    clear_cache()


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

    if (
        settings.use_antisniper_api
        and settings.antisniper_api_key is not None
        and api_key_is_valid(settings.antisniper_api_key)
    ):
        antisniper_key_holder = AntiSniperAPIKeyHolder(settings.antisniper_api_key)
    else:
        antisniper_key_holder = None

    state = OverlayState(
        lobby_players=set(),
        party_members=set(),
        set_api_key=functools.partial(
            set_api_key, settings=settings, hypixel_key_holder=hypixel_key_holder
        ),
        set_nickname=functools.partial(
            set_nickname, settings=settings, nick_database=nick_database
        ),
    )

    logpath = Path(logpath_string)

    with logpath.open("r", encoding="utf8", errors="replace") as logfile:
        # Process the entire logfile to get current player as well as potential
        # current party/lobby
        fast_forward_state(state, logfile.readlines())

    loglines = tail_file_with_reopen(logpath)

    denick = functools.partial(
        denick_with_api,
        nick_database=nick_database,
        antisniper_key_holder=antisniper_key_holder,
    )

    # Process the rest of the loglines as they come in
    if not overlay:
        process_loglines_to_stdout(
            state,
            hypixel_key_holder=hypixel_key_holder,
            antisniper_key_holder=antisniper_key_holder,
            denick=denick,
            loglines=loglines,
        )
    else:
        process_loglines_to_overlay(
            state,
            hypixel_key_holder=hypixel_key_holder,
            antisniper_key_holder=antisniper_key_holder,
            loglines=loglines,
            denick=denick,
            output_to_console=console,
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


def test() -> None:
    """Test the implementation on a static logfile or a list of loglines"""
    options = get_options(
        args=sys.argv[2:], default_settings_path=DEFAULT_SETTINGS_PATH
    )

    setup(logging.DEBUG, log_prefix="test_")

    slow, wait = False, 1
    get_stats = True
    overlay = True
    console = options.output_to_console

    stats_thread_count = 1 if get_stats else 0

    loglines: Iterable[str]
    if options.logfile_path is not None:
        loglines = options.logfile_path.open("r", encoding="utf8", errors="replace")
    else:
        loglines = [
            "(Client thread) Info Setting user: You",
            "(Client thread) Info [CHAT] You have joined [MVP++] Teammate's party!",
            "(Client thread) Info [CHAT] Teammate has joined (2/16)!",
            "(Client thread) Info [CHAT] You has joined (3/16)!",
            "(Client thread) Info [CHAT] ONLINE: You, Teammate, Hypixel",
            "(Client thread) Info [CHAT] Technoblade has joined (4/16)!",
            "(Client thread) Info [CHAT] Manhal_IQ_ has joined (5/16)!",
            "(Client thread) Info [CHAT] edater has joined (6/16)!",
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
    hypixel_key_holder = HypixelAPIKeyHolder(settings.hypixel_api_key)

    if (
        settings.use_antisniper_api
        and settings.antisniper_api_key is not None
        and api_key_is_valid(settings.antisniper_api_key)
    ):
        antisniper_key_holder = AntiSniperAPIKeyHolder(settings.antisniper_api_key)
    else:
        antisniper_key_holder = None

    state = OverlayState(
        lobby_players=set(),
        party_members=set(),
        set_api_key=functools.partial(
            set_api_key, settings=settings, hypixel_key_holder=hypixel_key_holder
        ),
        set_nickname=functools.partial(
            set_nickname, settings=settings, nick_database=nick_database
        ),
    )

    denick = functools.partial(
        denick_with_api,
        nick_database=nick_database,
        antisniper_key_holder=antisniper_key_holder,
    )

    if not overlay:
        process_loglines_to_stdout(
            state,
            hypixel_key_holder=hypixel_key_holder,
            antisniper_key_holder=antisniper_key_holder,
            denick=denick,
            loglines=loglines,
            thread_count=stats_thread_count,
        )
    else:
        process_loglines_to_overlay(
            state,
            hypixel_key_holder=hypixel_key_holder,
            antisniper_key_holder=antisniper_key_holder,
            loglines=loglines,
            denick=denick,
            output_to_console=console,
            thread_count=stats_thread_count,
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
    )


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        test()
    else:
        main()
