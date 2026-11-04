"""Debug dump: JSON with the inputs and outputs of each burst"""

import os
import platform
import sys
from dataclasses import dataclass
from typing import Any

from prism.overlay.state import OverlayState
from prism.overlay.tabshot.capture import Monitor
from prism.overlay.tabshot.screenshot import Team
from prism.overlay.tabshot.store import to_image_rect
from prism.overlay.tabshot.window import GameWindow, Rect


@dataclass(frozen=True, slots=True)
class PrismWindow:
    """The prism window, from Tk (logical px on Windows above 100 % DPI)"""

    rect: Rect
    shown: bool
    alpha: float


@dataclass(frozen=True, slots=True)
class CaptureInfo:
    file: str
    delay_ms: int  # Planned delay after the Tab press
    actual_delay_ms: float
    grab_ms: float
    teams: dict[str, Team] | None = None  # None: recognition did not run
    read_ms: float | None = None


def state_metadata(state: OverlayState, now: float) -> dict[str, Any]:
    return {
        "own_username": state.own_username,
        "party": sorted(state.party_members),
        "lobby": sorted(state.lobby_players),
        "alive": sorted(state.alive_players),
        "in_queue": state.in_queue,
        "out_of_sync": state.out_of_sync,
        "since_game_start_s": (
            None if state.last_game_start is None else now - state.last_game_start
        ),
        "bedwars_duel": state.bedwars_duel,
        "server": (
            None
            if state.server is None
            else {"host": state.server.host, "kind": state.server.kind}
        ),
    }


def window_metadata(window: GameWindow, origin: Monitor) -> dict[str, Any]:
    return {
        "rect": list(to_image_rect(window.rect, origin)),
        "screen_rect": list(window.rect),
        "pid": window.pid,
        "exe": window.exe,
        "class": window.window_class,
        "title": window.title,
        "foreground": window.foreground,
    }


def build_metadata(
    *,
    state: OverlayState,
    now: float,
    monitors: tuple[Monitor, ...],
    windows: list[GameWindow] | None,
    prism: PrismWindow | None,
    captures: list[CaptureInfo],
    known: list[str],
    pressed_at_unix: float,
    held_ms: float | None,
    thread_dpi_aware: bool,
) -> dict[str, Any]:
    """
    All `rect`s are in image px: [x, y, w, h] in the PNG (screen coords minus
    the origin of monitors[0]). `screen_rect`s are in screen coords.
    """
    origin = monitors[0]
    return {
        "version": 2,
        "os": sys.platform,
        "os_version": platform.platform(),
        "session": os.environ.get("XDG_SESSION_TYPE"),
        "thread_dpi_aware": thread_dpi_aware,
        "monitors": [
            {
                "rect": list(to_image_rect((m.left, m.top, m.width, m.height), origin)),
                "screen_rect": [m.left, m.top, m.width, m.height],
            }
            for m in monitors
        ],
        "windows": (
            None
            if windows is None
            else [window_metadata(window, origin) for window in windows]
        ),
        "prism": (
            None
            if prism is None
            else {
                "rect": list(to_image_rect(prism.rect, origin)),
                "screen_rect": list(prism.rect),
                "shown": prism.shown,
                "alpha": prism.alpha,
            }
        ),
        "tab": {"pressed_at_unix": pressed_at_unix, "held_ms": held_ms},
        "known": known,
        "captures": [
            {
                "file": c.file,
                "delay_ms": c.delay_ms,
                "actual_delay_ms": round(c.actual_delay_ms, 1),
                "grab_ms": round(c.grab_ms, 1),
                "teams": c.teams,
                "read_ms": None if c.read_ms is None else round(c.read_ms, 1),
            }
            for c in captures
        ],
        "state": state_metadata(state, now),
    }
