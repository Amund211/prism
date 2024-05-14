import logging

import pip_system_certs.wrapt_requests  # type: ignore  # noqa: F401

from prism.overlay.__main__ import main

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Exception caught in main!")
