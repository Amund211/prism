"""1.8.9 FontRenderer: char widths from the font texture, § codes, shadow,
bold and italic. Only the ascii page (chars 32-126) is drawn."""

import math
from collections.abc import Mapping

import numpy as np
import numpy.typing as npt

from synth.canvas import Canvas, Sprite

FONT_HEIGHT = 9
FORMAT_CODES = "0123456789abcdefklmnor"


def _color_codes() -> tuple[int, ...]:
    out = []
    for i in range(32):
        j = (i >> 3 & 1) * 85
        r = (i >> 2 & 1) * 170 + j
        g = (i >> 1 & 1) * 170 + j
        b = (i & 1) * 170 + j
        if i == 6:
            r += 85
        if i >= 16:
            r, g, b = r // 4, g // 4, b // 4
        out.append(r << 16 | g << 8 | b)
    return tuple(out)


COLOR_CODES = _color_codes()


def shadow_color(color: int) -> int:
    return (color & 0xFCFCFC) >> 2 | color & 0xFF000000


def parse_width_properties(text: str) -> dict[int, float]:
    """width.N=W lines of an OptiFine/MCPatcher ascii.properties"""
    out = {}
    for line in text.splitlines():
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("width.") and key[6:].isdigit() and int(key[6:]) < 256:
            out[int(key[6:])] = float(value)
    return out


class BitmapFont:
    """An ascii.png font: 16 x 16 cells; widths as FontRenderer.readFontTexture.

    hd: OptiFine HD rules for cells > 8 texels (Lunar uses them too): float
    widths last * 8 / cell + 1, space (cell * 5 // 16 + 1) texels, bold copy
    and bold advance + 0.5. widths: per-code overrides (OptiFine width.N).
    ink_alpha: min alpha of an ink texel for the width scan (vanilla 1;
    Lunar ignores faint texels, 26 = the draw alpha test fits)."""

    def __init__(
        self,
        texture: npt.NDArray[np.uint8],
        hd: bool = False,
        widths: Mapping[int, float] | None = None,
        ink_alpha: int = 1,
    ):
        h, w = texture.shape[:2]
        if w != h or w % 16 or texture.ndim != 3 or texture.shape[2] != 4:
            raise ValueError("font texture must be square RGBA, 16 x 16 cells")
        self.cell = w // 16
        self.hd = hd and self.cell > 8
        self.sprite = Sprite(texture, 16 * 8, 16 * 8)
        self.bold_offset = 0.5 if self.hd else 1.0
        cells = texture[..., 3].reshape(16, self.cell, 16, self.cell) >= ink_alpha
        ink = cells.transpose(0, 2, 3, 1).any(axis=3)  # [row, col, x]
        self.widths: list[float] = []
        for code in range(256):
            cols = np.flatnonzero(ink[code // 16, code % 16])
            last = int(cols[-1]) + 1 if len(cols) else 0
            if self.hd:
                self.widths.append(last * 8 / self.cell + 1)
            else:
                self.widths.append(float(int(0.5 + last * 8 / self.cell) + 1))
        self.space = (self.cell * 5 // 16 + 1) * 8 / self.cell if self.hd else 4.0
        for code, width in (widths or {}).items():
            self.widths[code] = width

    def char_width(self, c: str) -> float:
        if c == "§":
            return -1
        if c == " ":
            return self.space
        o = ord(c)
        return self.widths[o] if 32 < o < 127 else 0

    def string_width(self, text: str, bold_bug: bool = True) -> int:
        """getStringWidth, rounded like Math.round.
        bold_bug: a color code does not end bold (1.8.9)"""
        total, bold, j = 0.0, False, 0
        while j < len(text):
            w = self.char_width(text[j])
            if w < 0 and j < len(text) - 1:
                j += 1
                code = text[j].lower()
                if code == "l":
                    bold = True
                elif code == "r" or (not bold_bug and code in FORMAT_CODES[:16]):
                    bold = False
                w = 0
            total += w
            if bold and w > 0:
                total += self.bold_offset
            j += 1
        return int(math.floor(total + 0.5))


def _draw_pass(
    canvas: Canvas,
    font: BitmapFont,
    text: str,
    x: float,
    y: float,
    color: int,
    shadow: bool,
) -> float:
    if shadow:
        color = shadow_color(color)
    alpha = color & 0xFF000000
    base = color
    cur = color
    bold = italic = False
    pos = x
    i = 0
    while i < len(text):
        c = text[i]
        if c == "§" and i + 1 < len(text):
            code = FORMAT_CODES.find(text[i + 1].lower())
            if 0 <= code < 16:
                bold = italic = False
                cur = alpha | COLOR_CODES[code + (16 if shadow else 0)]
            elif code == 17:
                bold = True
            elif code == 20:
                italic = True
            elif code == 21:
                bold = italic = False
                # 1.8.9 bug: setColor(red, blue, green)
                cur = (
                    alpha | (base & 0xFF0000) | (base & 0xFF) << 8 | (base >> 8 & 0xFF)
                )
            i += 2
            continue
        w = font.char_width(c)
        o = ord(c)
        if c != " " and 32 < o < 127:
            _draw_char(canvas, font, o, pos, y, cur, italic, w)
            if bold:
                _draw_char(canvas, font, o, pos + font.bold_offset, y, cur, italic, w)
        if w > 0:
            pos += w + (font.bold_offset if bold else 0)
        i += 1
    return pos - x


def _draw_char(
    canvas: Canvas,
    font: BitmapFont,
    code: int,
    x: float,
    y: float,
    color: int,
    italic: bool,
    width: float,
) -> None:
    # renderDefaultChar: quad (width - 1.01) x 7.99, texture in 128-units
    u, v = code % 16 * 8, code // 16 * 8
    scale = font.cell / 8
    canvas.blit(
        font.sprite,
        x,
        y,
        w=width - 1.01,
        h=7.99,
        src=(u * scale, v * scale, (width - 1.01) * scale, 7.99 * scale),
        tint=color,
        skew=1.0 if italic else 0.0,
    )


def draw_string(
    canvas: Canvas,
    font: BitmapFont,
    text: str,
    x: float,
    y: float,
    color: int,
    shadow: bool = True,
) -> int:
    """drawString(WithShadow). color is RGB or ARGB. Returns the advance"""
    if color & 0xFC000000 == 0:
        color |= 0xFF000000
    if shadow:
        _draw_pass(canvas, font, text, x + 1, y + 1, color, True)
    return int(_draw_pass(canvas, font, text, x, y, color, False))
