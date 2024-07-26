import logging
from pathlib import Path

from appdirs import AppDirs

dirs = AppDirs(appname="prism_overlay")

CACHE_DIR = Path(dirs.user_cache_dir)
LOGDIR = Path(dirs.user_log_dir)

CONFIG_DIR = Path(dirs.user_config_dir)
DEFAULT_SETTINGS_PATH = CONFIG_DIR / "settings.toml"
DEFAULT_LOGFILE_CACHE_PATH = CONFIG_DIR / "known_logfiles.toml"

logger = logging.getLogger(__name__)


def ensure_directory(path: Path) -> bool:
    """Ensure directory exists"""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("Failed ensuring directory!")
        return False
    return True


def must_ensure_directory(path: Path) -> None:
    """Ensure directory exists"""
    if not ensure_directory(path):
        raise RuntimeError(f"Could not create directory '{path}'")
