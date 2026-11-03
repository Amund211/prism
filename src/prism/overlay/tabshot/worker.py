"""
Phase 1: take a burst of screenshots on each Tab press and save them.

The pynput callbacks only set state and put on a queue. All capture work
happens on the worker thread; PNG encoding on a separate saver thread.
"""

import logging
import os
import queue
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from prism.overlay.state import OverlayState
from prism.overlay.tabshot.capture import Grabber, RawCapture
from prism.overlay.tabshot.metadata import CaptureInfo, PrismWindow, build_metadata
from prism.overlay.tabshot.policy import burst_delays_ms, should_start_burst
from prism.overlay.tabshot.store import SampleStore, burst_stem, capture_filename
from prism.overlay.tabshot.window import GameWindow, find_game_windows

logger = logging.getLogger(__name__)

SAVE_QUEUE_SIZE = 24


def capture_supported() -> bool:  # pragma: nocover
    if sys.platform == "win32":
        return True
    if sys.platform == "linux":
        wayland = (
            os.environ.get("XDG_SESSION_TYPE") == "wayland"
            or "WAYLAND_DISPLAY" in os.environ
        )
        return not wayland and "DISPLAY" in os.environ
    # macOS: no Tab listener (pynput crash), so no trigger
    return False


class TabshotWorker:  # pragma: nocover
    def __init__(self, root: Path, get_state: Callable[[], OverlayState]) -> None:
        self.root = root
        self.get_state = get_state
        # Set from the Tk thread
        self.prism_window: PrismWindow | None = None

        self._presses: queue.Queue[tuple[float, float]] = queue.Queue(maxsize=1)
        self._saves: queue.Queue[Callable[[], None]] = queue.Queue(
            maxsize=SAVE_QUEUE_SIZE
        )
        self._released = threading.Event()
        self._released_at: float | None = None
        self._busy = False
        self._last_burst_start: float | None = None

    def start(self) -> None:
        logger.info(f"Tabshot: saving tab screenshots to {self.root}")
        threading.Thread(target=self._run, name="TabshotWorker", daemon=True).start()

    # pynput thread
    def on_tab_press(self) -> None:
        now = time.monotonic()
        self._released.clear()
        self._released_at = None
        if not should_start_burst(
            now=now, last_burst_start=self._last_burst_start, busy=self._busy
        ):
            return
        self._busy = True
        self._last_burst_start = now
        try:
            self._presses.put_nowait((now, time.time()))
        except queue.Full:
            self._busy = False

    # pynput thread
    def on_tab_release(self) -> None:
        self._released_at = time.monotonic()
        self._released.set()

    def _run(self) -> None:
        try:
            grabber = Grabber()
            store = SampleStore(self.root)
        except Exception:
            logger.exception("Tabshot: failed to start, no screenshots")
            return

        threading.Thread(
            target=self._save_loop, name="TabshotSaver", daemon=True
        ).start()

        while True:
            pressed_at, pressed_at_unix = self._presses.get()
            try:
                self._burst(grabber, store, pressed_at, pressed_at_unix)
            except Exception:
                logger.exception("Tabshot: burst failed")
            finally:
                self._busy = False

    def _save_loop(self) -> None:
        while True:
            job = self._saves.get()
            try:
                job()
            except Exception:
                logger.exception("Tabshot: failed to save")

    def _enqueue_save(self, job: Callable[[], None]) -> None:
        try:
            self._saves.put_nowait(job)
        except queue.Full:
            logger.warning("Tabshot: save queue full, dropping a file")

    def _burst(
        self,
        grabber: Grabber,
        store: SampleStore,
        pressed_at: float,
        pressed_at_unix: float,
    ) -> None:
        if not store.has_space():
            return

        wall = datetime.fromtimestamp(pressed_at_unix)
        stem = burst_stem(wall)
        directory = store.burst_dir(wall)
        state = self.get_state()
        prism = self.prism_window

        captures: list[CaptureInfo] = []
        # Save after the burst, so encoding does not slow down the grabs
        jobs: list[Callable[[], None]] = []
        monitors = None

        for delay_ms in burst_delays_ms():
            remaining = pressed_at + delay_ms / 1000 - time.monotonic()
            if remaining > 0:
                if self._released.wait(remaining):
                    break
            elif self._released.is_set():
                break

            start = time.monotonic()
            capture = grabber.grab_all()
            grab_ms = (time.monotonic() - start) * 1000
            monitors = capture.monitors

            filename = capture_filename(stem, delay_ms)
            jobs.append(_png_job(store, directory / filename, capture))
            captures.append(
                CaptureInfo(
                    file=filename,
                    delay_ms=delay_ms,
                    actual_delay_ms=(start - pressed_at) * 1000,
                    grab_ms=grab_ms,
                )
            )

        if monitors is None:
            return  # Released before the first capture

        windows: list[GameWindow] = find_game_windows()
        released_at = self._released_at
        metadata = build_metadata(
            state=state,
            now=pressed_at,
            monitors=monitors,
            windows=windows,
            prism=prism,
            captures=captures,
            pressed_at_unix=pressed_at_unix,
            held_ms=(
                None if released_at is None else (released_at - pressed_at) * 1000
            ),
            thread_dpi_aware=grabber.thread_dpi_aware,
        )
        path = directory / f"{stem}.json"
        for job in jobs:
            self._enqueue_save(job)
        self._enqueue_save(lambda: store.save_json(path, metadata))
        logger.info(f"Tabshot: {len(captures)} captures, {stem}")


def _png_job(
    store: SampleStore, path: Path, capture: RawCapture
) -> Callable[[], None]:  # pragma: nocover
    return lambda: store.save_png(path, capture)
