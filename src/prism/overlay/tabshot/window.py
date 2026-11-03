"""Find Minecraft windows. Best effort, only used as sample metadata."""

import logging
import sys
from dataclasses import dataclass
from pathlib import PurePath, PureWindowsPath

logger = logging.getLogger(__name__)

# (x, y, width, height) in physical screen px
Rect = tuple[int, int, int, int]

MINECRAFT_WINDOW_CLASSES = frozenset(("lwjgl", "glfw30"))
JAVA_EXE_NAMES = frozenset(("java", "javaw", "java.exe", "javaw.exe"))
MINECRAFT_HINTS = ("minecraft", "lunar", "badlion", "feather", "forge")


@dataclass(frozen=True, slots=True)
class GameWindow:
    rect: Rect  # Client area
    pid: int | None
    exe: str | None
    window_class: str | None
    title: str
    foreground: bool


def exe_name(exe: str) -> str:
    """Base name of an exe path, for Windows and posix paths"""
    if "\\" in exe:
        return PureWindowsPath(exe).name
    return PurePath(exe).name


def is_minecraft_candidate(
    *, exe: str | None, window_class: str | None, title: str
) -> bool:
    """Guess if a window is a Minecraft client window"""
    if window_class is not None and window_class.lower() in MINECRAFT_WINDOW_CLASSES:
        return True

    lower_title = title.lower()
    if any(hint in lower_title for hint in MINECRAFT_HINTS):
        return True

    if exe is not None:
        name = exe_name(exe).lower()
        if name in JAVA_EXE_NAMES:
            return True
        if any(hint in name for hint in MINECRAFT_HINTS):
            return True

    return False


def find_game_windows() -> list[GameWindow]:  # pragma: nocover
    """Find candidate Minecraft windows. Must run in the capture thread."""
    try:
        if sys.platform == "win32":
            from prism.overlay.tabshot.window_windows import find_windows

            return find_windows()
        if sys.platform == "linux":
            from prism.overlay.tabshot.window_x11 import find_windows

            return find_windows()
    except Exception:
        logger.exception("Failed to find game windows")
    return []
