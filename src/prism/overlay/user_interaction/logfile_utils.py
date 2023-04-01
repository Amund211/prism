import logging
import platform
from pathlib import Path

logger = logging.getLogger(__name__)


def suggest_logfile_candidates() -> list[Path]:  # pragma: nocover
    system = platform.system()
    if system == "Linux":
        lunar_client_base_dir = Path.home() / ".lunarclient" / "offline"

        try:
            lunar_client_logfiles = tuple(lunar_client_base_dir.rglob("latest.log"))
        except OSError:
            logger.exception(f"Could not rglob {lunar_client_base_dir}")
            lunar_client_logfiles = ()

        badlion_logfile = (
            Path.home()
            / ".minecraft"
            / "logs"
            / "blclient"
            / "minecraft"
            / "latest.log"
        )
        fml_logfile = Path.home() / ".minecraft" / "logs" / "fml-client-latest.log"
        pvplounge_logfile = Path.home() / ".pvplounge" / "logs" / "latest.log"
        vanilla_logfile = Path.home() / ".minecraft" / "logs" / "latest.log"

        return [
            *lunar_client_logfiles,
            badlion_logfile,
            fml_logfile,
            pvplounge_logfile,
            vanilla_logfile,
        ]
    elif system == "Darwin":
        lunar_client_base_dir = Path.home() / ".lunarclient" / "offline"

        try:
            lunar_client_logfiles = tuple(lunar_client_base_dir.rglob("latest.log"))
        except OSError:
            logger.exception(f"Could not rglob {lunar_client_base_dir}")
            lunar_client_logfiles = ()

        badlion_logfile = (
            Path.home()
            / "Library"
            / "Application Support"
            / "minecraft"
            / "logs"
            / "blclient"
            / "minecraft"
            / "latest.log"
        )
        fml_logfile = (
            Path.home()
            / "Library"
            / "Application Support"
            / "minecraft"
            / "logs"
            / "fml-client-latest.log"
        )
        pvplounge_logfile = (
            Path.home()
            / "Library"
            / "Application Support"
            / ".pvplounge"
            / "logs"
            / "latest.log"
        )
        vanilla_logfile = (
            Path.home()
            / "Library"
            / "Application Support"
            / "minecraft"
            / "logs"
            / "latest.log"
        )

        return [
            *lunar_client_logfiles,
            badlion_logfile,
            fml_logfile,
            pvplounge_logfile,
            vanilla_logfile,
        ]
    elif system == "Windows":
        lunar_client_base_dir = Path.home() / ".lunarclient" / "offline"

        try:
            lunar_client_logfiles = tuple(lunar_client_base_dir.rglob("latest.log"))
        except OSError:
            logger.exception(f"Could not rglob {lunar_client_base_dir}")
            lunar_client_logfiles = ()

        badlion_logfile = (
            Path.home()
            / "AppData"
            / "Roaming"
            / ".minecraft"
            / "logs"
            / "blclient"
            / "minecraft"
            / "latest.log"
        )
        fml_logfile = (
            Path.home()
            / "AppData"
            / "Roaming"
            / ".minecraft"
            / "logs"
            / "fml-client-latest.log"
        )
        pvplounge_logfile = (
            Path.home() / "AppData" / "Roaming" / ".pvplounge" / "logs" / "latest.log"
        )
        vanilla_logfile = (
            Path.home() / "AppData" / "Roaming" / ".minecraft" / "logs" / "latest.log"
        )
        return [
            *lunar_client_logfiles,
            badlion_logfile,
            fml_logfile,
            pvplounge_logfile,
            vanilla_logfile,
        ]
    else:
        # system == "Java"
        return []


def file_exists(path: Path | str) -> bool:
    """Return True if the file exists"""
    if isinstance(path, str):
        path = Path(path)

    try:
        return path.is_file()
    except OSError:  # pragma: nocover
        logger.exception(f"Could not call ({path=}).is_file()")
        return False


def suggest_logfiles() -> tuple[str, ...]:
    """Suggest logfile candidates that exist"""
    return tuple(map(str, filter(file_exists, suggest_logfile_candidates())))


def get_timestamp(path_str: str) -> float:
    """Get the modified timestamp of the file"""
    try:
        stat = Path(path_str).stat()
    except OSError:
        logger.exception(f"Could not stat {path_str=}")
        return 0
    else:
        return stat.st_mtime
