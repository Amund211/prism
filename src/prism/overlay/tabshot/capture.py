"""Screen capture with mss. Create and use a Grabber in one thread only."""

import ctypes
import logging
import sys
from dataclasses import dataclass

import mss

logger = logging.getLogger(__name__)

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
_PER_MONITOR_AWARE_V2 = -4


@dataclass(frozen=True, slots=True)
class Monitor:
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class RawCapture:
    """Raw BGRA pixels of all monitors (monitors[0] is the bounding box)"""

    bgra: bytes
    monitors: tuple[Monitor, ...]


def make_thread_dpi_aware() -> bool:  # pragma: nocover
    """
    Make only this thread per-monitor DPI aware (Windows), so window rects and
    captures are in physical px. The process (and Tk) stays unaware.
    """
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        old = user32.SetThreadDpiAwarenessContext(_PER_MONITOR_AWARE_V2)
    except Exception:
        logger.exception("Failed to set thread DPI awareness")
        return False
    if not old:
        logger.warning("SetThreadDpiAwarenessContext failed")
        return False
    return True


def _patch_mss_process_dpi_awareness() -> None:  # pragma: nocover
    """mss sets process DPI awareness on Windows, which would change Tk"""
    if sys.platform != "win32":
        return
    from mss.windows import gdi

    setattr(gdi.MSSImplGdi, "_set_dpi_awareness", lambda self: None)


class Grabber:  # pragma: nocover
    def __init__(self) -> None:
        _patch_mss_process_dpi_awareness()
        self.thread_dpi_aware = make_thread_dpi_aware()
        self._sct = mss.mss()

    def grab_all(self) -> RawCapture:
        # Re-read the monitors each time: monitors can change while prism runs
        self._sct._monitors = None
        monitors = tuple(
            Monitor(m["left"], m["top"], m["width"], m["height"])
            for m in self._sct.monitors
        )
        shot = self._sct.grab(self._sct.monitors[0])
        return RawCapture(bgra=shot.bgra, monitors=monitors)

    def close(self) -> None:
        self._sct.close()
