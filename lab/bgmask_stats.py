"""bgmask_stats.py            stats per font: residual of the model, mask px vs shadow mask
bgmask_stats.py view sub   save a picture: row band / shadow mask / bg mask"""

import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

import grid3
from bgmask import bg_mask, cell_diff
from data import image, label, train_names
from textmask import Shadow

HERE = Path(__file__).parent


def stats():
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
