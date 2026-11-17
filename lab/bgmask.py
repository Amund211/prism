"""Idea 1 POC: text mask from the predicted cell background.

cell = separator * (1 - 32/255) + 32 per channel (0x20FFFFFF over the panel).
Predict each cell pixel from the separator row above and the one below; a
pixel that fits neither prediction is not background (glyph or shadow).

bgmask.py            stats per font: residual of the model, mask px vs shadow mask
bgmask.py view sub   save a picture: row band / shadow mask / bg mask
"""
import os
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent

T = int(os.environ.get("BG_T", 18))
BRIGHT = 72  # text has max channel >= 85; shadows are <= 63
A = 1 - 32 / 255


def predict(sep: np.ndarray) -> np.ndarray:
    return sep.astype(np.float32) * A + 32


def cell_diff(rgb, y, k, x0, x1):
    """8k x W: distance (max channel) of each cell pixel to the nearer of the
    two background predictions (from the separator above / below)"""
    H = rgb.shape[0]
    cell = rgb[y : y + 8 * k, x0:x1].astype(np.float32)
    up = predict(rgb[max(0, y - 1), x0:x1])
    dn = predict(rgb[min(H - 1, y + 8 * k), x0:x1])
    du = np.abs(cell - up[None]).max(axis=2)
    dd = np.abs(cell - dn[None]).max(axis=2)
    return np.minimum(du, dd)


def bg_mask(rgb, g, t=T, glyph_only=True):
    """Full-image bool mask of non-background pixels in the text part of
    each cell (after the head, before the ping icon)."""
    k = g.k
    m = np.zeros(rgb.shape[:2], bool)
    for x0, x1 in g.cols:
        a, b = x0 + 9 * k, x1 - 11 * k
        if b <= a:
            continue
        for y in g.tops:
            if y + 8 * k >= rgb.shape[0]:
                continue
            d = cell_diff(rgb, y, k, a, b) >= t
            if glyph_only:
                d &= rgb[y : y + 8 * k, a:b].max(axis=2) >= BRIGHT
            m[y : y + 8 * k, a:b] = d
    return m


def stats():
    import grid3
    from data import image, label, train_names
    from textmask import Shadow

    by = defaultdict(lambda: [0, 0, 0, [], 0])
    for n in train_names():
        lab = label(n)
        want = len(lab["rows"]) + len(lab["npcs"])
        rgb = image(n)
        g = grid3.find_grid(rgb)
        if g is None or len(g.tops) != want or "lunar" in n or len(g.cols) != 1:
            continue
        k = g.k
        x0, x1 = g.cols[0]
        a, b = x0 + 9 * k, x1 - 11 * k
        sh = Shadow(rgb).mask(k)
        bm = bg_mask(rgb, g)
        res = []
        for y in g.tops:
            res.append(np.median(cell_diff(rgb, y, k, a, b)))
        f = lab["setup"]["font"] or "none"
        e = by[f]
        e[0] += len(g.tops)
        ys = np.array(g.tops)
        e[1] += sum(int(sh[y : y + 8 * k, a:b].sum()) for y in ys) / (k * k)
        e[2] += sum(int(bm[y : y + 8 * k, a:b].sum()) for y in ys) / (k * k)
        e[3].extend(res)
        e[4] += 1
    print(f"{'font':30s} imgs rows  shadow px/row  bg px/row  ratio  median bg residual")
    for f, (rows, s, bgp, res, ni) in sorted(by.items()):
        print(f"{f:30s} {ni:4d} {rows:4d} {s / rows:10.1f} {bgp / rows:10.1f} {bgp / max(1, s):6.2f} {np.median(res):8.2f}")


def view(sub):
    import grid3
    from data import image, train_names
    from textmask import Shadow

    for n in train_names():
        if sub not in n:
            continue
        rgb = image(n)
        g = grid3.find_grid(rgb)
        k = g.k
        x0, x1 = g.cols[0]
        y0, y1 = g.tops[0], g.tops[-1] + 8 * k
        sh = Shadow(rgb).mask(k)[y0:y1, x0:x1]
        bm = bg_mask(rgb, g)[y0:y1, x0:x1]
        raw = bg_mask(rgb, g, glyph_only=False)[y0:y1, x0:x1]
        to3 = lambda m: np.repeat((m * 255).astype(np.uint8)[..., None], 3, axis=2)
        im = np.concatenate([rgb[y0:y1, x0:x1], to3(sh), to3(bm), to3(raw)], axis=1)
        f = max(1, min(4, 1900 // im.shape[1]))
        im = cv2.resize(im, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST)
        out = HERE / "crops" / f"bg_{n}.png"
        cv2.imwrite(str(out), im[..., ::-1])
        print(out, "k", k, im.shape)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "view":
        view(sys.argv[2])
    else:
        stats()
