import sys

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    import os

    # Set the version to disable version calculation, which crashes in the bundle
    os.environ["PBR_VERSION"] = "5.8.0"

import logging

from examples.overlay.__main__ import main

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"Exception caught in main '{e}'")
