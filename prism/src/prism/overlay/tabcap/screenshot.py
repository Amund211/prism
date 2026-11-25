from typing import TYPE_CHECKING, Literal, TypeAlias

# NOTE: PIL is imported lazily. The macOS build excludes it (no universal2 wheel)
if TYPE_CHECKING:  # pragma: nocover
    from PIL import Image

Team: TypeAlias = Literal[
    "red", "blue", "green", "yellow", "aqua", "white", "pink", "gray"
]
TEAMS: frozenset[Team] = frozenset(
    ("red", "blue", "green", "yellow", "aqua", "white", "pink", "gray")
)

# In-memory screenshot. Never written to disk by the overlay.
Screenshot: TypeAlias = "Image.Image"


def from_bgra(bgra: bytes, width: int, height: int) -> Screenshot:
    """Convert a raw BGRA capture (e.g. mss `ScreenShot.bgra`) to RGB"""
    from PIL import Image

    return Image.frombytes("RGB", (width, height), bgra, "raw", "BGRX")
