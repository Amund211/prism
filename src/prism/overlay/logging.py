import logging
import platform
from datetime import date, datetime
from itertools import count

from prism import VERSION_STRING
from prism.overlay.directories import LOGDIR, must_ensure_directory

logger = logging.getLogger(__name__)


def setup_logging(
    loglevel: int = logging.WARNING, log_prefix: str = ""
) -> None:  # pragma: nocover
    must_ensure_directory(LOGDIR)

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

    # Capture Python warnings to the logfile with logger py.warnings
    logging.captureWarnings(True)

    # Log system+version info
    current_datestring = datetime.now().isoformat(timespec="seconds")
    logger.setLevel(logging.DEBUG)
    logger.debug(f"Starting prism overlay {VERSION_STRING} at {current_datestring}")
    logger.debug(f"Running on {platform.uname()}. Python {platform.python_version()}")
    logger.setLevel(loglevel)
