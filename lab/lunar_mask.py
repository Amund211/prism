"""Letter mask on ping rows (Lunar: no row cells).

Lunar draws one panel and no cells, so the row band and the gap rows show
the same panel over the world. Glyphs use GUI rows 0-6 (shadow 1-7) and GUI
row 8 is empty, so the background of each row pixel is predicted by the gap
row above (y - 1) and below (y + 8k), with no colour change (cell = separator
x 1, not x 0.875 + 32 as with cells).

lunar_mask.py   residual of the model per image (Lunar train images)
"""

import os

import numpy as np

T = int(os.environ.get("LM_T", 18))
BRIGHT = 72


def row_diff(rgb, y, k, x0, x1):
    H = rgb.shape[0]
    band = rgb[y : y + 8 * k, x0:x1].astype(np.int16)
    up = rgb[max(0, y - 1), x0:x1].astype(np.int16)
    dn = rgb[min(H - 1, y + 8 * k), x0:x1].astype(np.int16)
    du = np.abs(band - up[None]).max(axis=2)
    dd = np.abs(band - dn[None]).max(axis=2)
    return np.minimum(du, dd)


def lunar_mask(rgb, g, t=T):
    """Same contract as bgmask.bg_mask: full-image bool mask of glyph pixels
    in the text part of each row"""
    k = g.k
    m = np.zeros(rgb.shape[:2], bool)
    for x0, x1 in g.cols:
        a, b = x0 + 9 * k, x1 - 11 * k
        if b <= a:
            continue
        for y in g.tops:
            if y + 8 * k >= rgb.shape[0]:
                continue
            d = row_diff(rgb, y, k, a, b) >= t
            d &= rgb[y : y + 8 * k, a:b].max(axis=2) >= BRIGHT
            m[y : y + 8 * k, a:b] = d
    return m


if __name__ == "__main__":
    import ping_grid
    from data import image, train_names

    for n in train_names():
        if "lunar" not in n:
            continue
        rgb = image(n)
        g = ping_grid.find_ping(rgb)
        if g is None:
            continue
        k = g.k
        x0, x1 = g.cols[0]
        res = np.concatenate([row_diff(rgb, y, k, x0 + 9 * k, x1 - 11 * k).ravel() for y in g.tops])
        m = lunar_mask(rgb, g)
        print(f"{n:62s} residual median {np.median(res):4.1f} p75 {np.quantile(res, 0.75):5.1f}"
              f" mask px/row {m.sum() / len(g.tops):6.1f}")
