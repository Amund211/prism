import logging
import os
import time
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def watch_file_with_reopen(
    path: Path, start_at: int, reopen_timeout: float, poll_timeout: float
) -> Iterable[str]:
    """Iterate over new lines in a file, reopen the file when stale"""
    last_position = start_at

    while True:
        with path.open("r", encoding="utf8", errors="replace") as f:
            date_openend = date.today()
            last_read = time.monotonic()

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
                    time_since_last_read = time.monotonic() - last_read
                    new_day = date.today() != date_openend

                    if time_since_last_read > reopen_timeout:
                        # > `reopen_timeout` seconds since last read -> reopen file
                        logger.debug(f"Timed out reading file '{path}'; reopening")
                        break
                    elif (
                        new_day
                        and time_since_last_read
                        > reopen_timeout / 5  # More sensitive reopen_timeout
                        and datetime.now().second > 5  # Wait for the new logfile
                    ):
                        # New day, new logfile. Reopen
                        logger.info("Reopening logfile due to rotation at midnight")
                        break

                    time.sleep(poll_timeout)
                    continue

                last_read = time.monotonic()
                yield line
