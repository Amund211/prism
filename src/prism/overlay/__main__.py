"""
Parse the chat on Hypixel to detect players in your party and bedwars lobby

Run from the root dir by `python -m prism.overlay [--logfile <path-to-logfile>]`
"""

import sys
from pathlib import Path

from prism.overlay.commandline import get_options
from prism.overlay.directories import (
    CONFIG_DIR,
    DEFAULT_LOGFILE_CACHE_PATH,
    DEFAULT_SETTINGS_PATH,
    must_ensure_directory,
)
from prism.overlay.logging import setup_logging
from prism.overlay.nick_database import NickDatabase
from prism.overlay.not_parallel import ensure_not_parallel
from prism.overlay.process_loglines import watch_from_logfile
from prism.overlay.settings import get_settings
from prism.overlay.threading import recommend_stats_thread_count
from prism.overlay.user_interaction.get_logfile import prompt_for_logfile_path


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
        from prism.overlay.testing import test

        test()
    else:
        main()
