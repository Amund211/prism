"""Phase 1 only: save tab-list samples (PNG + JSON) to disk"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from prism.overlay.tabshot.capture import Monitor, RawCapture
from prism.overlay.tabshot.screenshot import from_bgra
from prism.overlay.tabshot.window import Rect

logger = logging.getLogger(__name__)

MAX_BYTES = 20 * 1024**3
MAX_FILES = 50_000


def to_image_rect(rect: Rect, origin: Monitor) -> Rect:
    """Screen rect -> rect in the all-monitors image"""
    x, y, w, h = rect
    return (x - origin.left, y - origin.top, w, h)


def burst_stem(now: datetime) -> str:
    return now.strftime("%H%M%S.") + f"{now.microsecond // 1000:03d}"


def capture_filename(stem: str, delay_ms: int) -> str:
    return f"{stem}-{delay_ms:04d}ms.png"


class SampleStore:
    def __init__(
        self, root: Path, *, max_bytes: int = MAX_BYTES, max_files: int = MAX_FILES
    ) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self.max_files = max_files
        self.full = False
        self._bytes, self._files = self._usage()

    def _usage(self) -> tuple[int, int]:
        total, count = 0, 0
        if not self.root.exists():
            return 0, 0
        for dirpath, _, filenames in os.walk(self.root):
            for filename in filenames:
                try:
                    total += (Path(dirpath) / filename).stat().st_size
                except OSError:  # pragma: nocover
                    continue
                count += 1
        return total, count

    def has_space(self) -> bool:
        if not self.full and (
            self._bytes >= self.max_bytes or self._files >= self.max_files
        ):
            self.full = True
            logger.warning(
                f"Tabshot store full ({self._files} files, {self._bytes} bytes). "
                f"Not saving more to {self.root}"
            )
        return not self.full

    def burst_dir(self, now: datetime) -> Path:
        return self.root / now.strftime("%Y-%m-%d")

    def _account(self, path: Path) -> None:
        self._bytes += path.stat().st_size
        self._files += 1

    def save_png(self, path: Path, capture: RawCapture) -> None:
        if not self.has_space():
            return
        bbox = capture.monitors[0]
        image = from_bgra(capture.bgra, bbox.width, bbox.height)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, format="PNG", compress_level=1)
        self._account(path)

    def save_json(self, path: Path, data: dict[str, Any]) -> None:
        if not self.has_space():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf8")
        self._account(path)
