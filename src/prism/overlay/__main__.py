"""
Parse the chat on Hypixel to detect players in your party and bedwars lobby

Run from the root dir by `python -m prism.overlay [--logfile <path-to-logfile>]`
"""

import logging
import sys
import time
from collections.abc import Iterable
from pathlib import Path

from prism.overlay.commandline import get_options
from prism.overlay.controller import RealOverlayController
from prism.overlay.directories import (
    CONFIG_DIR,
    DEFAULT_LOGFILE_CACHE_PATH,
    DEFAULT_SETTINGS_PATH,
    must_ensure_directory,
)
from prism.overlay.logging import setup_logging
from prism.overlay.nick_database import NickDatabase
from prism.overlay.not_parallel import ensure_not_parallel
from prism.overlay.process_loglines import (
    process_loglines_to_overlay,
    process_loglines_to_stdout,
    watch_from_logfile,
)
from prism.overlay.settings import get_settings
from prism.overlay.state import OverlayState
from prism.overlay.threading import recommend_stats_thread_count
from prism.overlay.user_interaction.get_logfile import prompt_for_logfile_path

logger = logging.getLogger(__name__)


def slow_iterable(
    iterable: Iterable[str], wait: float = 1
) -> Iterable[str]:  # pragma: nocover
    """Wait `wait` seconds between each yield from iterable"""
    # Used for testing
    for item in iterable:
        time.sleep(wait)
        print(f"Yielding '{item}'")
        yield item
    print("Done yielding")


def test() -> None:  # pragma: nocover
    """Test the implementation on a static logfile or a list of loglines"""
    options = get_options(
        args=sys.argv[2:], default_settings_path=DEFAULT_SETTINGS_PATH
    )

    ensure_not_parallel()

    setup_logging(logging.DEBUG, log_prefix="test_")

    slow, wait = False, 1
    overlay = True
    console = options.output_to_console

    loglines: Iterable[str]
    if options.logfile_path is not None:
        loglines = options.logfile_path.open("r", encoding="utf8", errors="replace")
    else:
        CHAT = "(Client thread) Info [CHAT] "
        loglines = [
            "(Client thread) Info Setting user: Testing",
            f"{CHAT}You have joined [MVP++] Teammate's party!",
            f"{CHAT}You'll be partying with: Notch",
            f"{CHAT}Teammate has joined (2/16)!",  # out of sync
            f"{CHAT}Testing has joined (3/16)!",
            f"{CHAT}ONLINE: Testing, Teammate, Hypixel",  # in sync
            f"{CHAT}Technoblade has joined (4/16)!",
            f"{CHAT}Manhal_IQ_ has joined (5/16)!",
            f"{CHAT}edater has joined (6/16)!",  # denicked by api
            f"{CHAT}SomeUnknownNick has joined (7/16)!",  # Nicked teammate
            # f"{CHAT}               Bed Wars ",  # game start
            f"{CHAT}Hypixel was killed by Testing. FINAL KILL!",
            # f"{CHAT}1st Killer - [MVP+] Player1",  # game end
        ]

    if slow:
        loglines = slow_iterable(loglines, wait=wait)

    settings = get_settings(options.settings_path, default_stats_thread_count=8)

    with settings.mutex:
        default_database = {
            nick: value["uuid"] for nick, value in settings.known_nicks.items()
        }

    nick_database = NickDatabase.from_disk([], default_database=default_database)

    # watch_from_logfile
    state = OverlayState()

    controller = RealOverlayController(
        state=state,
        settings=settings,
        nick_database=nick_database,
    )

    if not overlay:
        process_loglines_to_stdout(controller, loglines=loglines)
    else:
        process_loglines_to_overlay(
            controller,
            loglines=loglines,
            output_to_console=console,
        )


def main(*nick_databases: Path) -> None:  # pragma: nocover
    """Run the overlay"""
    options = get_options(default_settings_path=DEFAULT_SETTINGS_PATH)

    ensure_not_parallel()

    setup_logging(options.loglevel)

    must_ensure_directory(CONFIG_DIR)

    # Read settings and populate missing values
    settings = get_settings(
        options.settings_path,
        recommend_stats_thread_count(),
    )

    if options.logfile_path is None:
        logfile_path = prompt_for_logfile_path(
            DEFAULT_LOGFILE_CACHE_PATH, settings.autoselect_logfile
        )
    else:
        logfile_path = options.logfile_path

    with settings.mutex:
        default_database = {
            nick: value["uuid"] for nick, value in settings.known_nicks.items()
        }

    nick_database = NickDatabase.from_disk(
        list(nick_databases), default_database=default_database
    )

    watch_from_logfile(
        logfile_path,
        overlay=True,
        console=options.output_to_console,
        settings=settings,
        nick_database=nick_database,
    )


if __name__ == "__main__":  # pragma: nocover
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        test()
    else:
        main()
