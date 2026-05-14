import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs


@dataclass(frozen=True, slots=True)
class PrismDirs:
    cache_dir: Path
    log_dir: Path
    config_dir: Path
    settings_path: Path
    logfile_cache_path: Path


def get_dirs() -> PrismDirs:
    pd = PlatformDirs(appname="prism_overlay")
    cache_dir = Path(pd.user_cache_dir)
    config_dir = Path(pd.user_config_dir)
    # Linux: keep logs under the cache dir. platformdirs' user_log_dir lives
    # under $XDG_STATE_HOME, but existing prism installs have logs in cache.
    log_dir = cache_dir / "log" if sys.platform == "linux" else Path(pd.user_log_dir)
    return PrismDirs(
        cache_dir=cache_dir,
        log_dir=log_dir,
        config_dir=config_dir,
        settings_path=config_dir / "settings.toml",
        logfile_cache_path=config_dir / "known_logfiles.toml",
    )


dirs = get_dirs()

CACHE_DIR = dirs.cache_dir
LOGDIR = dirs.log_dir
CONFIG_DIR = dirs.config_dir
DEFAULT_SETTINGS_PATH = dirs.settings_path
DEFAULT_LOGFILE_CACHE_PATH = dirs.logfile_cache_path

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
