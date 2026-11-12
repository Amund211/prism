"""
Take a screenshot on each Tab press, read the teams from it, and save the
image + inputs + outputs to disk (debug dump). The result is not used yet.

The pynput callbacks only set state and put on a queue. All capture and
recognition work happens on the worker thread; PNG encoding on a separate
saver thread.
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
from typing import TYPE_CHECKING, Any

from prism.overlay.state import OverlayState
from prism.overlay.tabshot.capture import Grabber, RawCapture
from prism.overlay.tabshot.game_info import safe_collect_game_info
from prism.overlay.tabshot.metadata import CaptureInfo, PrismWindow, build_metadata
from prism.overlay.tabshot.policy import (
    CAPTURE_DELAYS_MS,
    known_names,
    should_start_burst,
)
from prism.overlay.tabshot.processes import list_processes
from prism.overlay.tabshot.screenshot import Team, from_bgra
from prism.overlay.tabshot.store import SampleStore, burst_stem, capture_filename
from prism.overlay.tabshot.window import GameWindow, find_game_windows

if TYPE_CHECKING:  # pragma: nocover
    from collections.abc import Iterable

    from prism.overlay.tabshot.screenshot import Screenshot

    ReadTeams = Callable[[Screenshot, Iterable[str]], dict[str, Team]]

logger = logging.getLogger(__name__)

SAVE_QUEUE_SIZE = 32


def _load_read_teams() -> "ReadTeams":  # pragma: nocover
    # Use one BLAS thread, so recognition does not take every core from the game
    for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(var, "1")
    # Lazy: numpy, scipy and PIL are not in the macOS build
    from prism.overlay.tabshot.teams import read_teams

    return read_teams


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
    def __init__(
        self,
        root: Path,
        get_state: Callable[[], OverlayState],
        on_teams: Callable[[OverlayState, dict[str, Team]], None] | None = None,
    ) -> None:
        self.root = root
        self.get_state = get_state
        # Called on the worker thread with the state at Tab press
        self.on_teams = on_teams
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

        read_teams: "ReadTeams | None" = None
        try:
            read_teams = _load_read_teams()
        except Exception:
            logger.exception("Tabshot: failed to load team recognition")

        threading.Thread(
            target=self._save_loop, name="TabshotSaver", daemon=True
        ).start()

        while True:
            pressed_at, pressed_at_unix = self._presses.get()
            try:
                self._burst(grabber, store, read_teams, pressed_at, pressed_at_unix)
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

    def _call_on_teams(self, state: OverlayState, teams: dict[str, Team]) -> None:
        if self.on_teams is None:
            return
        try:
            self.on_teams(state, teams)
        except Exception:
            logger.exception("Tabshot: on_teams failed")

    def _enqueue_save(self, job: Callable[[], None]) -> None:
        try:
            self._saves.put_nowait(job)
        except queue.Full:
            logger.warning("Tabshot: save queue full, dropping a file")

    def _burst(
        self,
        grabber: Grabber,
        store: SampleStore,
        read_teams: "ReadTeams | None",
        pressed_at: float,
        pressed_at_unix: float,
    ) -> None:
        if not store.has_space():
            return

        wall = datetime.fromtimestamp(pressed_at_unix)
        stem = burst_stem(wall)
        directory = store.burst_dir(wall)
        state = self.get_state()
        known = known_names(state)
        prism = self.prism_window

        captures: list[CaptureInfo] = []
        monitors = None
        best = 0  # Most teams read in one capture of this burst

        for delay_ms in CAPTURE_DELAYS_MS:
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
            # Save now: a long burst would hold too many raw captures in memory
            self._enqueue_save(_png_job(store, directory / filename, capture))

            teams, read_ms = _read(read_teams, capture, known)
            captures.append(
                CaptureInfo(
                    file=filename,
                    delay_ms=delay_ms,
                    actual_delay_ms=(start - pressed_at) * 1000,
                    grab_ms=grab_ms,
                    teams=teams,
                    read_ms=read_ms,
                )
            )
            # Trial branch: capture all delays while held. Show the best read.
            if teams is not None and len(teams) > best:
                best = len(teams)
                self._call_on_teams(state, teams)

        if best == 0 and any(c.teams is not None for c in captures):
            self._call_on_teams(state, {})  # Clear old colors: this read failed

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
            known=known,
            pressed_at_unix=pressed_at_unix,
            held_ms=(
                None if released_at is None else (released_at - pressed_at) * 1000
            ),
            thread_dpi_aware=grabber.thread_dpi_aware,
        )
        path = directory / f"{stem}.json"
        self._enqueue_save(
            lambda: store.save_json(path, _with_game_info(store, metadata))
        )
        last = captures[-1]
        logger.info(
            f"Tabshot: {stem}, {len(captures)} captures, "
            f"{'no' if last.teams is None else len(last.teams)} teams "
            f"of {len(known)} known, read {last.read_ms or 0:.0f} ms"
        )


def _read(
    read_teams: "ReadTeams | None", capture: RawCapture, known: list[str]
) -> tuple[dict[str, Team] | None, float | None]:  # pragma: nocover
    """(teams, ms). (None, None) if recognition is off or failed"""
    if read_teams is None:
        return None, None
    start = time.monotonic()
    try:
        bbox = capture.monitors[0]
        teams = read_teams(from_bgra(capture.bgra, bbox.width, bbox.height), known)
    except Exception:
        logger.exception("Tabshot: team recognition failed")
        return None, None
    return teams, (time.monotonic() - start) * 1000


def _with_game_info(
    store: SampleStore, metadata: dict[str, Any]
) -> dict[str, Any]:  # pragma: nocover
    """Trial branch: add client info. Runs on the saver thread (slow parts)."""
    try:
        processes = list_processes()
    except Exception:
        logger.exception("Tabshot: failed to list processes")
        processes = None
    return {
        **metadata,
        "game": safe_collect_game_info(store.root),
        "processes": processes,
    }


def _png_job(
    store: SampleStore, path: Path, capture: RawCapture
) -> Callable[[], None]:  # pragma: nocover
    return lambda: store.save_png(path, capture)
