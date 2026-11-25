import numpy as np

from synth.text import BitmapFont


def block_font(
    cell: int = 8,
    ink: dict[str, int] | None = None,
    hd: bool = False,
    widths: dict[int, float] | None = None,
) -> BitmapFont:
    """Own test font: every glyph is a white block, `ink[c]` texels wide
    (default 5 * cell / 8), full cell height. No real font is used."""
    ink = ink or {}
    tex = np.zeros((16 * cell, 16 * cell, 4), np.uint8)
    for code in range(33, 127):
        w = ink.get(chr(code), 5 * cell // 8)
        x, y = code % 16 * cell, code // 16 * cell
        tex[y : y + cell, x : x + w] = 255
    return BitmapFont(tex, hd=hd, widths=widths)
