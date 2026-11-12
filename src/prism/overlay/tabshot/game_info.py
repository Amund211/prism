"""
Trial branch: game client metadata for tab screenshots (launcher, version, GUI
scale, resource packs, ...). Best effort: every failure gives None / empty.

NOTE: logs and launcher files can hold session tokens. Never copy a logfile, and
never copy files with account / token names.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import time
from collections.abc import Sequence
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any

logger = logging.getLogger(__name__)

# Set by process_loglines when the logfile is chosen
_active_logfile: str | None = None

LOG_HEAD_BYTES = 256 * 1024
MAX_COPY_BYTES = 2 * 1024 * 1024
REDACTED = "<redacted>"

GAME_DIR_FILES = (
    "options.txt",
    "optionsof.txt",
    "optionsLC.txt",
    "optionsshaders.txt",
    "badlion_settings.json",
    "iris.properties",
    "sodium-options.json",
)
PARSED_OPTION_FILES = ("options.txt", "optionsof.txt", "optionsLC.txt")
LUNAR_SETTINGS_FILES = (
    "global_options.json",
    "profile_manager.json",
    "features.json",
    "version",
)
LUNAR_PROFILE_FILES = ("mods.json", "general.json", "performance.json")
INSTANCE_FILES = ("instance.cfg", "mmc-pack.json")
NEVER_COPY = ("account", "token", "credential", "msa", "session")

LOG_PATTERNS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = tuple(
    (re.compile(pattern), keys)
    for pattern, keys in (
        (r"Setting user: (\S+)", ("user",)),
        (
            r"Forge Mod Loader version (\S+) for Minecraft (\S+)",
            ("forge", "minecraft"),
        ),
        (
            r"Loading Minecraft (\S+) with Fabric Loader (\S+)",
            ("fabric_minecraft", "fabric"),
        ),
        (r"Java is .*?, version (\S+?),", ("java",)),
        (r"LWJGL Version: (\S+)", ("lwjgl",)),
        (r"OptiFine_(\S+)", ("optifine",)),
        (r"MC Version: (\S+)", ("badlion_mc",)),
        (r"BLC Version: (\S+)", ("badlion",)),
        (r"\]: Width: (\d+)", ("badlion_width",)),
        (r"\]: Height: (\d+)", ("badlion_height",)),
        (r"FullScreen: (\w+)", ("badlion_fullscreen",)),
        (r"Minecraft Version: (\S+)", ("minecraft_version",)),
        (r"Launched Version: (\S+)", ("launched_version",)),
    )
)
LUNAR_MARKERS = ("LUNARCLIENT_STATUS_INIT", "com.moonsworth.lunar")

CMDLINE_VALUE_FLAGS = (
    "version",
    "gameDir",
    "assetsDir",
    "assetIndex",
    "launcherVersion",
    "texturesDir",
    "versionType",
    "width",
    "height",
)


def set_active_logfile(path: str | os.PathLike[str] | None) -> None:
    global _active_logfile
    _active_logfile = None if path is None else str(path)


def get_active_logfile() -> str | None:
    return _active_logfile


def _pure(path: str) -> PurePath:
    return PureWindowsPath(path) if "\\" in path else PurePosixPath(path)


def _join(parts: Sequence[str], like: PurePath) -> str:
    return str(type(like)(*parts))


def detect_launcher(logfile: str) -> dict[str, str | None]:
    """Guess the launcher and its dirs from the logfile path"""
    path = _pure(logfile)
    parts = path.parts
    lower = [part.lower() for part in parts]
    result: dict[str, str | None] = {
        "launcher": "unknown",
        "profile": None,
        "game_dir": None,
        "launcher_dir": None,
        "instance_dir": None,
        "minecraft_dir": None,
    }

    if ".lunarclient" in lower:
        i = lower.index(".lunarclient")
        result["launcher"] = "lunar"
        result["launcher_dir"] = _join(parts[: i + 1], path)
        # Lunar profiles share the resource packs in .minecraft
        home = parts[:i]
        if isinstance(path, PureWindowsPath):
            minecraft_dir = _join((*home, "AppData", "Roaming", ".minecraft"), path)
        else:
            minecraft_dir = _join((*home, ".minecraft"), path)
        result["minecraft_dir"] = minecraft_dir
        kind = lower[i + 1] if len(parts) > i + 2 else None
        if kind == "profiles":
            result["profile"] = parts[i + 2]
            result["game_dir"] = _join(parts[: i + 3], path)
        elif kind == "offline":
            result["profile"] = f"offline/{parts[i + 2]}"
            result["game_dir"] = minecraft_dir
        return result

    if lower[-3:-1] == ["blclient", "minecraft"]:
        result["launcher"] = "badlion"
        result["game_dir"] = str(path.parents[3])
        return result

    if "instances" in lower[:-1]:
        i = lower.index("instances")
        if 0 < i and len(parts) > i + 2:
            result["launcher"] = lower[i - 1]
            result["profile"] = parts[i + 1]
            result["launcher_dir"] = _join(parts[:i], path)
            result["instance_dir"] = _join(parts[: i + 2], path)
            result["game_dir"] = str(path.parent.parent)
            return result

    if ".pvplounge" in lower:
        result["launcher"] = "pvplounge"
    elif path.name.lower() == "fml-client-latest.log":
        result["launcher"] = "forge"
    elif path.parent.name.lower() == "logs":
        result["launcher"] = "minecraft_launcher"
    else:
        return result

    result["game_dir"] = str(path.parent.parent)
    return result


def parse_log_head(text: str) -> dict[str, Any]:
    """Version info from the start of a logfile. Only regex matches are kept."""
    first = re.match(r"\[(\d\d:\d\d:\d\d)\]", text)
    result: dict[str, Any] = {"first_line_time": first.group(1) if first else None}
    for pattern, keys in LOG_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            result.update(zip(keys, match.groups()))
    if any(marker in text for marker in LUNAR_MARKERS):
        result["lunar"] = True
    return result


def parse_options(text: str) -> dict[str, Any]:
    """Parse options.txt style (key:value) or JSON (Lunar optionsLC.txt)"""
    if text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    result: dict[str, Any] = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            result[key] = value
    return result


def _is_sensitive(flag: str) -> bool:
    name = flag.lstrip("-").lower()
    return any(word in name for word in ("token", "session", "xuid", "clientid"))


def redact_cmdline(args: Sequence[str]) -> list[str]:
    result: list[str] = []
    redact_next = False
    for arg in args:
        if redact_next:
            result.append(REDACTED)
            redact_next = False
        elif re.match(r"eyJ[\w-]+\.", arg):
            result.append(REDACTED)
        elif arg.startswith("-") and "=" in arg:
            flag, _, _ = arg.partition("=")
            result.append(f"{flag}={REDACTED}" if _is_sensitive(flag) else arg)
        else:
            result.append(arg)
            redact_next = arg.startswith("-") and _is_sensitive(arg)
    return result


def parse_cmdline(args: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for i, arg in enumerate(args):
        if arg.startswith("-Xmx"):
            result["xmx"] = arg[4:]
        elif arg.startswith("--") and arg[2:] in CMDLINE_VALUE_FLAGS:
            if i + 1 < len(args):
                result[arg[2:]] = args[i + 1]
    return result


def _read_text(path: Path, limit: int | None = None) -> str | None:
    try:
        with path.open("rb") as f:
            data = f.read() if limit is None else f.read(limit)
    except OSError:
        return None
    return data.decode("utf8", errors="replace")


def _stat(path: Path) -> dict[str, Any] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return {"size": stat.st_size, "mtime": stat.st_mtime}


def _list_dir(path: Path) -> list[str] | None:
    try:
        return sorted(child.name for child in path.iterdir())
    except OSError:
        return None


def _settings_files(launcher: dict[str, str | None]) -> list[tuple[str, Path]]:
    """(snapshot path, source path) for the settings files to copy"""
    files: list[tuple[str, Path]] = []
    if launcher["game_dir"]:
        game_dir = Path(launcher["game_dir"])
        files += [(f"game/{name}", game_dir / name) for name in GAME_DIR_FILES]
    if launcher["minecraft_dir"] and launcher["minecraft_dir"] != launcher["game_dir"]:
        minecraft_dir = Path(launcher["minecraft_dir"])
        files += [
            (f"minecraft/{name}", minecraft_dir / name) for name in GAME_DIR_FILES
        ]
    if launcher["instance_dir"]:
        instance_dir = Path(launcher["instance_dir"])
        files += [(f"instance/{name}", instance_dir / name) for name in INSTANCE_FILES]
    if launcher["launcher"] == "lunar" and launcher["launcher_dir"]:
        game = Path(launcher["launcher_dir"]) / "settings" / "game"
        prefix = "launcher/settings/game"
        files += [(f"{prefix}/{name}", game / name) for name in LUNAR_SETTINGS_FILES]
        try:
            profiles = sorted(p for p in game.iterdir() if p.is_dir())
        except OSError:  # pragma: nocover
            profiles = []
        for profile in profiles:
            files += [
                (f"{prefix}/{profile.name}/{name}", profile / name)
                for name in LUNAR_PROFILE_FILES
            ]
    return [
        (dest, src)
        for dest, src in files
        if not any(word in dest.lower() for word in NEVER_COPY)
    ]


def snapshot_settings(
    files: list[tuple[str, Path]], root: Path
) -> tuple[str | None, dict[str, bytes]]:
    """
    Copy the files to root/settings/<content hash>/ once. Returns the snapshot
    dir relative to root (None if no files) and the contents read.
    """
    contents: dict[str, bytes] = {}
    sources: dict[str, Any] = {}
    for dest, src in files:
        try:
            if not src.is_file() or src.stat().st_size > MAX_COPY_BYTES:
                continue
            contents[dest] = src.read_bytes()
        except OSError:  # pragma: nocover
            continue
        sources[dest] = {"source": str(src), **(_stat(src) or {})}

    if not contents:
        return None, contents

    digest = hashlib.sha256()
    for dest in sorted(contents):
        digest.update(dest.encode() + b"\0" + contents[dest] + b"\0")
    name = f"settings/{digest.hexdigest()[:16]}"
    target = root / name
    if target.is_dir():
        return name, contents

    tmp = root / "settings" / f".tmp-{os.getpid()}-{time.monotonic_ns()}"
    try:
        for dest, data in contents.items():
            (tmp / dest).parent.mkdir(parents=True, exist_ok=True)
            (tmp / dest).write_bytes(data)
        (tmp / "manifest.json").write_text(
            json.dumps({"created_unix": time.time(), "files": sources}, indent=2),
            encoding="utf8",
        )
        tmp.rename(target)
    except OSError:  # pragma: nocover
        # Another writer may have won the race
        shutil.rmtree(tmp, ignore_errors=True)
        if not target.is_dir():
            raise
    return name, contents


def collect_game_info(logfile: str | None, root: Path) -> dict[str, Any]:
    """Everything we can learn about the game client from files on disk"""
    info: dict[str, Any] = {
        "logfile": logfile,
        "logfile_stat": None,
        "launcher": None,
        "log_head": None,
        "options": {},
        "resourcepacks_dir": None,
        "minecraft_resourcepacks_dir": None,
        "settings_snapshot": None,
    }
    if logfile is None:
        return info

    launcher = detect_launcher(logfile)
    info["launcher"] = launcher
    path = Path(logfile)
    info["logfile_stat"] = _stat(path)
    head = _read_text(path, LOG_HEAD_BYTES)
    if head is not None:
        info["log_head"] = parse_log_head(head)

    if launcher["game_dir"]:
        info["resourcepacks_dir"] = _list_dir(
            Path(launcher["game_dir"]) / "resourcepacks"
        )
    if launcher["minecraft_dir"]:
        info["minecraft_resourcepacks_dir"] = _list_dir(
            Path(launcher["minecraft_dir"]) / "resourcepacks"
        )

    try:
        snapshot, contents = snapshot_settings(_settings_files(launcher), root)
    except Exception:
        logger.exception("Tabshot: failed to snapshot settings")
        snapshot, contents = None, {}
    info["settings_snapshot"] = snapshot

    for name in PARSED_OPTION_FILES:
        data = contents.get(f"game/{name}")
        if data is not None:
            info["options"][name] = parse_options(data.decode("utf8", errors="replace"))
    return info


def safe_collect_game_info(root: Path) -> dict[str, Any] | None:  # pragma: nocover
    try:
        return collect_game_info(get_active_logfile(), root)
    except Exception:
        logger.exception("Tabshot: failed to collect game info")
        return None
