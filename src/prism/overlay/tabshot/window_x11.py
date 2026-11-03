"""Find Minecraft windows on X11 (python-xlib, a pynput dep on Linux)"""

import os
from typing import Any

from Xlib import X, display  # type: ignore [import-untyped]

from prism.overlay.tabshot.window import GameWindow, is_minecraft_candidate


def _prop(d: Any, window: Any, name: str) -> Any:
    prop = window.get_full_property(d.intern_atom(name), X.AnyPropertyType)
    return None if prop is None else prop.value


def _exe(pid: int | None) -> str | None:
    if pid is None:
        return None
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None


def find_windows() -> list[GameWindow]:
    d = display.Display()
    try:
        root = d.screen().root
        active = _prop(d, root, "_NET_ACTIVE_WINDOW")
        active_id = int(active[0]) if active is not None and len(active) else None
        client_ids = _prop(d, root, "_NET_CLIENT_LIST")
        if client_ids is None:
            return []

        windows = []
        for window_id in client_ids:
            window = d.create_resource_object("window", int(window_id))

            name = _prop(d, window, "_NET_WM_NAME")
            if name is None:
                name = _prop(d, window, "WM_NAME")
            if isinstance(name, bytes):
                name = name.decode("utf8", errors="replace")
            title = name or ""

            wm_class = window.get_wm_class()
            window_class = wm_class[1] if wm_class else None

            pid_prop = _prop(d, window, "_NET_WM_PID")
            pid = int(pid_prop[0]) if pid_prop is not None and len(pid_prop) else None
            exe = _exe(pid)

            if not is_minecraft_candidate(
                exe=exe, window_class=window_class, title=title
            ):
                continue

            geometry = window.get_geometry()
            coords = root.translate_coords(window, 0, 0)
            windows.append(
                GameWindow(
                    rect=(coords.x, coords.y, geometry.width, geometry.height),
                    pid=pid,
                    exe=exe,
                    window_class=window_class,
                    title=title,
                    foreground=int(window_id) == active_id,
                )
            )
        return windows
    finally:
        d.close()
