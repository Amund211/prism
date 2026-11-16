"""Minecraft 1.8.9 bitmap font (ascii.png): glyphs, widths, rendering."""

from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image

ASCII = Path.home() / "git/overlay/resource_packs/vanilla/1.8.9/assets/minecraft/textures/font/ascii.png"
FONTS = Path.home() / "git/overlay/resource_packs/fonts"


@cache
def load(path: Path = ASCII) -> dict[str, np.ndarray]:
    """{char: bool glyph (h x w)}; w = advance - 1 (the 1 px gap excluded)"""
    im = np.asarray(Image.open(path).convert("RGBA"))
    cell = im.shape[0] // 16
    glyphs = {}
    for code in range(32, 127):
        cy, cx = divmod(code, 16)
        g = im[cy * cell : (cy + 1) * cell, cx * cell : (cx + 1) * cell, 3] > 0
        cols = np.flatnonzero(g.any(axis=0))
        if code == 32:
            glyphs[" "] = np.zeros((cell, cell // 2 - 1), bool)  # space advance 4 (at 8 px)
            continue
        w = cols.max() + 1 if len(cols) else 0
        glyphs[chr(code)] = g[:, :w]
    return glyphs


def width(text: str, glyphs: dict[str, np.ndarray] | None = None) -> int:
    """Text width in font px, without the trailing gap"""
    g = glyphs or load()
    return sum(g.get(c, g["?"]).shape[1] + 1 for c in text) - 1


def render(text: str, k: int = 1, glyphs: dict[str, np.ndarray] | None = None) -> np.ndarray:
    g = glyphs or load()
    parts = []
    h = next(iter(g.values())).shape[0]
    for c in text:
        gl = g.get(c, g["?"])
        parts.append(gl)
        parts.append(np.zeros((h, 1), bool))
    img = np.concatenate(parts[:-1], axis=1) if parts else np.zeros((h, 0), bool)
    if k > 1:
        img = img.repeat(k, axis=0).repeat(k, axis=1)
    return img


def char_widths(text: str, glyphs: dict[str, np.ndarray] | None = None) -> list[int]:
    g = glyphs or load()
    return [g.get(c, g["?"]).shape[1] for c in text]
