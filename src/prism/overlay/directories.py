import logging
from dataclasses import dataclass
from pathlib import Path

from appdirs import AppDirs


@dataclass(frozen=True, slots=True)
class PrismDirs:
    cache_dir: Path
    log_dir: Path
    config_dir: Path
    settings_path: Path
    logfile_cache_path: Path


def get_dirs() -> PrismDirs:
    app_dirs = AppDirs(appname="prism_overlay")
    config_dir = Path(app_dirs.user_config_dir)
    return PrismDirs(
        cache_dir=Path(app_dirs.user_cache_dir),
        log_dir=Path(app_dirs.user_log_dir),
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
