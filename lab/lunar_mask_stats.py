"""lunar_mask_stats.py: residual of the lunar_mask model per image (Lunar train images)."""

import numpy as np

import ping_grid
from data import image, train_names
from lunar_mask import lunar_mask, row_diff

if __name__ == "__main__":
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
