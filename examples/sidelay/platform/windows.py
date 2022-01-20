import logging

import win32con  # type: ignore
import win32gui  # type: ignore

logger = logging.getLogger(__name__)

fullscreen_toggled = False


def set_windowstate(hwnd: int, fullscreen: bool = True) -> None:
    """Set a window to be borderless windowed/regular maximized"""
    style_BL = (
        win32con.WS_DLGFRAME
        | win32con.WS_CLIPSIBLINGS
        | win32con.WS_CLIPCHILDREN
        | win32con.WS_VISIBLE
    )
    style_Normal = (
        win32con.WS_DLGFRAME
        | win32con.WS_CLIPSIBLINGS
        | win32con.WS_CLIPCHILDREN
        | win32con.WS_VISIBLE
        | win32con.WS_BORDER
        | win32con.WS_DLGFRAME
        | win32con.WS_SYSMENU
        | win32con.WS_THICKFRAME
        | win32con.WS_MINIMIZEBOX
        | win32con.WS_MAXIMIZEBOX
    )
    if fullscreen:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style_BL)
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    else:
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style_Normal)
        win32gui.MoveWindow(hwnd, 100, 100, 1000, 600, False)
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)


def set_minecraft_windowstate(fullscreen: bool) -> None:
    """Try finding the minecraft window and setting it borderless"""
    hwnd = win32gui.FindWindow("LWJGL", None)

    if hwnd is None:
        logger.error("Could not find Minecraft window.")
        return

    set_windowstate(hwnd, fullscreen)


def toggle_fullscreen() -> None:
    """Toggle minecraft maximized/borderless fullscreen"""
    global fullscreen_toggled
    fullscreen_toggled = not fullscreen_toggled
    set_minecraft_windowstate(fullscreen_toggled)
