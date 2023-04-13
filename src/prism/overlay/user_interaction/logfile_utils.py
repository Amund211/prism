import logging
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Self

import toml

logger = logging.getLogger(__name__)


# Thresholds for logfiles to be considered recent/really recent
LOGFILE_RECENT_THRESHOLD_SECONDS = 60
LOGFILE_REALLY_RECENT_THRESHOLD_SECONDS = 5


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


def suggest_logfiles() -> tuple[Path, ...]:
    """Suggest logfile candidates that exist"""
    return tuple(filter(file_exists, suggest_logfile_candidates()))


def get_timestamp(path: Path) -> float:
    """Get the modified timestamp of the file"""
    try:
        stat = path.stat()
    except (OSError, FileNotFoundError):
        logger.exception(f"Could not stat {path=}")
        return 0
    else:
        return stat.st_mtime


def safe_resolve_existing_path(path_str: str) -> Path | None:
    """Resolve a path string into a Path that exists, or None"""
    try:
        return Path(path_str).resolve(strict=True)
    except (FileNotFoundError, RuntimeError):
        return None


@dataclass(frozen=True, slots=True)
class ActiveLogfile:
    id_: int
    path: Path
    age_seconds: float

    @property
    def recent(self) -> bool:
        """Return True if the logfile is recently used"""
        return self.age_seconds <= LOGFILE_RECENT_THRESHOLD_SECONDS

    @property
    def really_recent(self) -> bool:
        """Return True if the logfile is really recently used"""
        return self.age_seconds <= LOGFILE_REALLY_RECENT_THRESHOLD_SECONDS

    def get_age_interval(self, interval_length: float = 10) -> int:
        """
        Return which interval the age is in

        Used for sorting logfiles to prevent the list from shuffling around too much
        """
        return int(self.age_seconds // interval_length)

    def refresh_age(self) -> Self:
        """Construct a new ActiveLogfile with an updated age"""
        return self.with_age(id_=self.id_, path=self.path)

    @classmethod
    def with_age(cls, id_: int, path: Path) -> Self:
        """Construct an ActiveLogfile by getting the current age of the path"""
        return cls(id_=id_, path=path, age_seconds=time.time() - get_timestamp(path))


def create_active_logfiles(
    logfile_paths: tuple[Path, ...]
) -> tuple[ActiveLogfile, ...]:
    """Create a tuple of ActiveLogfile instances from a tuple of paths"""

    return tuple(
        sorted(
            (
                ActiveLogfile.with_age(id_=index, path=path)
                for index, path in enumerate(logfile_paths)
            ),
            key=ActiveLogfile.get_age_interval,
        )
    )


def refresh_active_logfiles(
    active_logfiles: tuple[ActiveLogfile, ...]
) -> tuple[ActiveLogfile, ...]:
    """Return a sorted tuple of ActiveLogfile instances with updated ages"""
    return tuple(
        sorted(
            (active_logfile.refresh_age() for active_logfile in active_logfiles),
            key=ActiveLogfile.get_age_interval,
        )
    )


def autoselect_logfile(
    active_logfiles: tuple[ActiveLogfile, ...],
    selected_id: int,
    last_used_id: int | None,
) -> ActiveLogfile | None:
    """The active logfiles tuple must be sorted"""
    if not active_logfiles:
        return None

    candidate = active_logfiles[0]

    if (
        candidate.really_recent  # It's really recent, and the only recent one
        and not any(active_logfile.recent for active_logfile in active_logfiles[1:])
        and candidate.id_ == last_used_id  # It's our last used logfile
        and selected_id == last_used_id  # It's selected
    ):
        return candidate
    return None


@dataclass
class LogfileCache:
    known_logfiles: tuple[Path, ...]
    last_used_index: int | None


def read_logfile_cache(logfile_cache_path: Path) -> tuple[LogfileCache, bool]:
    """Read the logfile cache and resolve the strings into paths"""
    logfile_cache_updated = False

    try:
        logfile_cache = toml.load(logfile_cache_path)
    except Exception:
        logger.exception("failed loading logfile cache")
        logfile_cache = {}
        logfile_cache_updated = True

    read_known_logfiles = logfile_cache.get("known_logfiles", None)
    if not isinstance(read_known_logfiles, (list, tuple)):
        read_known_logfiles = ()
        logfile_cache_updated = True

    last_used = logfile_cache.get("last_used", None)
    if last_used is not None and not isinstance(last_used, str):
        last_used = None
        logfile_cache_updated = True

    known_logfile_strings = list(
        filter(
            lambda el: isinstance(el, str),
            read_known_logfiles,
        )
    )

    known_logfiles: list[Path] = []
    last_used_index: int | None = None

    index = 0
    seen = set[str]()
    while known_logfile_strings:
        logfile_string = known_logfile_strings.pop(0)

        # Deduplicate the logfile list
        if logfile_string in seen:
            continue
        seen.add(logfile_string)

        logfile_path = safe_resolve_existing_path(logfile_string)

        if logfile_path is None:
            continue

        known_logfiles.append(logfile_path)
        if last_used == logfile_string:
            last_used_index = index

        index += 1

    if len(known_logfiles) != len(read_known_logfiles):
        # Some logfiles were deduplicated or removed as missing
        logfile_cache_updated = True

    if last_used is not None and last_used_index is None:
        # last_used not present in known_logfiles
        logfile_cache_updated = True

    return (
        LogfileCache(
            known_logfiles=tuple(known_logfiles), last_used_index=last_used_index
        ),
        logfile_cache_updated,
    )


def write_logfile_cache(logfile_cache_path: Path, cache: LogfileCache) -> None:
    known_logfiles = tuple(map(str, cache.known_logfiles))
    last_used = (
        known_logfiles[cache.last_used_index]
        if cache.last_used_index is not None
        and 0 <= cache.last_used_index < len(known_logfiles)
        else None
    )
    with logfile_cache_path.open("w") as cache_file:
        toml.dump(
            {"known_logfiles": known_logfiles, "last_used": last_used}, cache_file
        )


def get_logfile(
    update_cache: Callable[[tuple[ActiveLogfile, ...], int | None], LogfileCache],
    logfile_cache_path: Path,
    autoselect: bool,
) -> Path | None:
    """Select a logfile, fallback to the provided function"""
    old_cache, logfile_cache_updated = read_logfile_cache(logfile_cache_path)

    # Add newly discovered logfiles
    new_logfiles = set(suggest_logfiles()) - set(old_cache.known_logfiles)
    if new_logfiles:
        old_cache.known_logfiles += tuple(new_logfiles)

    last_used_id = old_cache.last_used_index
    active_logfiles = create_active_logfiles(old_cache.known_logfiles)

    autoselected = None
    if autoselect and last_used_id is not None:
        autoselected = autoselect_logfile(
            active_logfiles,
            selected_id=last_used_id,
            last_used_id=last_used_id,
        )

    if autoselected is not None:
        # Autoselection will always choose the first item because it assumes
        # the tuple of sorted logfiles to be sorted
        cache = LogfileCache(known_logfiles=old_cache.known_logfiles, last_used_index=0)
    else:
        cache = update_cache(active_logfiles, last_used_id)

    if cache.last_used_index is not None and (
        cache.known_logfiles != old_cache.known_logfiles
        or cache.last_used_index != old_cache.last_used_index
        or logfile_cache_updated
    ):
        write_logfile_cache(logfile_cache_path, cache)

    selected_index = cache.last_used_index

    if selected_index is None:
        return None

    if 0 <= selected_index < len(cache.known_logfiles):
        selected = cache.known_logfiles[selected_index]
        logger.info(f"Selected logfile {selected}")
        return selected
    else:  # pragma: no coverage
        raise ValueError(f"Selected index out of range! {cache}")
