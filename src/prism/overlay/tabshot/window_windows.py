"""Find Minecraft windows on Windows. Call from a per-monitor DPI-aware thread."""

import ctypes
from ctypes import wintypes

import win32gui  # type: ignore [import-untyped]
import win32process  # type: ignore [import-untyped]

from prism.overlay.tabshot.window import GameWindow, is_minecraft_candidate

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_kernel32 = ctypes.WinDLL(  # type: ignore [attr-defined, unused-ignore]
    "kernel32", use_last_error=True
)


def _process_exe(pid: int) -> str | None:
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None
        return buf.value
    finally:
        _kernel32.CloseHandle(handle)


def find_windows() -> list[GameWindow]:
    foreground = win32gui.GetForegroundWindow()
    hwnds: list[int] = []

    def callback(hwnd: int, _: object) -> bool:
        if win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd):
            hwnds.append(hwnd)
        return True

    win32gui.EnumWindows(callback, None)

    windows = []
    for hwnd in hwnds:
        title = win32gui.GetWindowText(hwnd)
        window_class = win32gui.GetClassName(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        exe = _process_exe(pid)
        if not is_minecraft_candidate(exe=exe, window_class=window_class, title=title):
            continue

        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        x, y = win32gui.ClientToScreen(hwnd, (left, top))
        windows.append(
            GameWindow(
                rect=(x, y, right - left, bottom - top),
                pid=pid,
                exe=exe,
                window_class=window_class,
                title=title,
                foreground=hwnd == foreground,
            )
        )
    return windows
