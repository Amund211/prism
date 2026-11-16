"""i1_dbg.py <image> [max]: print first glyph of each layer segment + class."""

import sys

import numpy as np

import e2c_rowband as rb
import h5_layer as h5
import i1_layer as L
from data import image
from textmask import Shadow


def art(m: np.ndarray) -> str:
    return "\n".join("".join("#" if v else "." for v in r) for r in m)


def main() -> None:
    rgb = image(sys.argv[1])
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    bs = rb.bands(rgb)
    k = bs[0][3]
    sh = Shadow(rgb).mask(k)
    h, w, _ = rgb.shape
    n = 0
    for y, x0, x1, k in bs:
        y0, y1 = max(0, y - k), min(h - k, y + 9 * k)
        x0 = max(0, x0 - h5.WIDEN * k)
        x1 = min(w - k, x1 + h5.WIDEN // 4 * k)
        sub = sh[y0:y1:k, x0:x1:k]
        ys, xs = np.nonzero(sub)
        if len(ys) < 12:
            continue
        iy, ix = y0 + ys * k, x0 + xs * k
        t = h5.hue(rgb[iy, ix])
        t = np.where(t >= 0, t, h5.hue(rgb[iy + k, ix + k], 4))
        px = rgb[y0:y1:k, x0:x1:k]
        for ti in np.unique(t):
            if ti < 0 or (t == ti).sum() < 12:
                continue
            m = np.zeros(sub.shape, bool)
            m[ys[t == ti], xs[t == ti]] = True
            m = h5.fill(px, m)
            for a, b in h5.segments(m):
                seg = m[:, a:b]
                fg = L.first_glyph(seg)
                cls = L.classify(fg[0][1:9]) if fg else None
                if "--odd" in sys.argv and (cls is None or cls[0] == L.LETTER[h5.TEAMS[ti]]):
                    continue
                print(h5.TEAMS[ti], y, "cls", cls, "info", L.letter_info(seg, px[:, a:b]))
                print(art(seg[:, :40]))
                n += 1
                if n >= lim:
                    return


if __name__ == "__main__":
    main()
