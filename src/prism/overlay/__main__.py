"""
Parse the chat on Hypixel to detect players in your party and bedwars lobby

Run from the root dir by `python -m prism.overlay [--logfile <path-to-logfile>]`
"""

import logging

import truststore

from prism.overlay.commandline import get_options
from prism.overlay.directories import (
    CONFIG_DIR,
    DEFAULT_SETTINGS_PATH,
    must_ensure_directory,
)
from prism.overlay.logging import setup_logging
from prism.overlay.nick_database import NickDatabase
from prism.overlay.not_parallel import ensure_not_parallel
from prism.overlay.settings import get_settings
from prism.overlay.state import OverlayState
from prism.overlay.thread_count import recommend_stats_thread_count


def main() -> None:  # pragma: nocover
    """Run the overlay"""
    options = get_options(default_settings_path=DEFAULT_SETTINGS_PATH)

    ensure_not_parallel()

    if options.test:
        setup_logging(logging.DEBUG, log_prefix="test_")
    else:
        setup_logging(options.loglevel)

    must_ensure_directory(CONFIG_DIR)

    # Read settings and populate missing values
    settings = get_settings(
        options.settings_path,
        recommend_stats_thread_count(),
    )

    if not settings.use_included_certs:
        # Patch requests to use system certs
        truststore.inject_into_ssl()

    with settings.mutex:
        default_database = {
            nick: value["uuid"] for nick, value in settings.known_nicks.items()
        }

    nick_database = NickDatabase.from_disk([], default_database=default_database)

    # Import late so we can patch ssl certs in requests
    from prism.overlay.controller import RealOverlayController
    from prism.overlay.process_loglines import process_loglines, prompt_and_read_logfile

    controller = RealOverlayController(
        state=OverlayState(),
        settings=settings,
        nick_database=nick_database,
    )

    if options.test_ssl:
        from prism.overlay.testing import test_ssl

        test_ssl()
        return

    if options.test:
        from prism.overlay.testing import get_test_loglines

        loglines = get_test_loglines(options)
    else:
        loglines = prompt_and_read_logfile(controller, options, settings)

    process_loglines(
        controller=controller,
        loglines=loglines,
        overlay=True,
        console=options.output_to_console,
    )


if __name__ == "__main__":  # pragma: nocover
    main()
