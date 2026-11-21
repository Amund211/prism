"""Float RGB canvas in screen pixels, drawn on in GUI units like 1.8.9 does.

Values stay float and are rounded once in image(): the captures match a
single rounding (black 128 then black 32 in the Lunar slots), not a round
after each layer.
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

RGBImage = npt.NDArray[np.uint8]


@dataclass(frozen=True)
class Sprite:
    """RGBA texels drawn on a gui_w x gui_h GUI px quad (nearest texel)"""

    texels: npt.NDArray[np.uint8]
    gui_w: float
    gui_h: float

    def __post_init__(self) -> None:
        if self.texels.ndim != 3 or self.texels.shape[2] != 4:
            raise ValueError("Sprite texels must be H x W x 4 (RGBA)")


class Canvas:
    def __init__(self, background: RGBImage, k: int) -> None:
        if background.ndim != 3 or background.shape[2] != 3:
            raise ValueError("background must be H x W x 3 (RGB)")
        if k < 1:
            raise ValueError("GUI scale must be >= 1")
        self.buf = background.astype(np.float64)
        self.background = self.buf.copy()
        self.ink = np.zeros(background.shape[:2], bool)  # pixels drawn by blit
        self.k = k

    @property
    def gui_width(self) -> int:
        return math.ceil(int(self.buf.shape[1]) / self.k)

    @property
    def gui_height(self) -> int:
        return math.ceil(int(self.buf.shape[0]) / self.k)

    def image(self) -> RGBImage:
        return np.clip(np.floor(self.buf + 0.5), 0, 255).astype(np.uint8)

    def fill_rect(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        color: int,
        alpha: int,
        over_background: bool = False,
    ) -> None:
        """Blend a rect. over_background: blend over the original background
        (replaces what was drawn there before)"""
        k = self.k
        ys = slice(max(0, y0 * k), max(0, y1 * k))
        xs = slice(max(0, x0 * k), max(0, x1 * k))
        under = (self.background if over_background else self.buf)[ys, xs]
        rgb = np.array([color >> 16 & 255, color >> 8 & 255, color & 255], np.float64)
        self.buf[ys, xs] = rgb * alpha / 255 + under * (255 - alpha) / 255

    def blit(
        self,
        sprite: Sprite,
        x: float,
        y: float,
        *,
        w: float | None = None,
        h: float | None = None,
        src: tuple[float, float, float, float] | None = None,
        tint: int = 0xFFFFFFFF,
        skew: float = 0.0,
    ) -> None:
        """Draw `src` (u, v, du, dv in texels; default: the whole sprite) on the
        quad at GUI (x, y), size w x h (default: the sprite's GUI size).
        tint is ARGB and multiplies the texels. skew moves the top edge right
        and the bottom edge left (italic). Alpha test: drop alpha <= 0.1."""
        w = sprite.gui_w if w is None else w
        h = sprite.gui_h if h is None else h
        th, tw = sprite.texels.shape[:2]
        u0, v0, du, dv = src if src is not None else (0.0, 0.0, float(tw), float(th))
        k = self.k
        hgt, wid = self.buf.shape[:2]
        py0 = max(0, math.floor(y * k))
        py1 = min(hgt, math.ceil((y + h) * k))
        px0 = max(0, math.floor((x - abs(skew)) * k))
        px1 = min(wid, math.ceil((x + w + abs(skew)) * k))
        if py0 >= py1 or px0 >= px1:
            return
        gy = (np.arange(py0, py1) + 0.5) / k - y  # t inside the quad
        gx = (np.arange(px0, px1) + 0.5) / k
        shift = skew - 2 * skew * gy / h
        s = gx[None, :] - (x + shift[:, None])
        inside = (gy[:, None] >= 0) & (gy[:, None] < h) & (s >= 0) & (s < w)
        u = np.clip(np.floor(u0 + s * du / w), 0, tw - 1).astype(int)
        v = np.clip(np.floor(v0 + gy * dv / h), 0, th - 1).astype(int)
        v = np.broadcast_to(v[:, None], u.shape)
        tex = sprite.texels[v, u].astype(np.float64)
        tint_rgb = np.array([tint >> 16 & 255, tint >> 8 & 255, tint & 255])
        a = tex[..., 3] / 255 * ((tint >> 24 & 255) / 255)
        draw = inside & (a > 0.1)
        rgb = tex[..., :3] * tint_rgb / 255
        region = self.buf[py0:py1, px0:px1]
        a3 = a[..., None]
        region[draw] = (rgb * a3 + region * (1 - a3))[draw]
        self.ink[py0:py1, px0:px1] |= draw
