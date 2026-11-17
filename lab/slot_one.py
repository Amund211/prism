"""slot_one.py <image> <name>: spans of the letter slot of one row"""

import sys

import numpy as np

from bgmask import bg_mask
from data import image, label
from j3_slot import grid_parse
from rows import runs_of

n, who = sys.argv[1], sys.argv[2]
lab = label(n)
rgb = image(n)
g, tab, prows = grid_parse(rgb, slot=False)
bm = bg_mask(rgb, g)
k, nt = g.k, len(g.tops)
i = [r["name"] for r in lab["rows"]].index(who)
p = next(p for p in prows if (p.row.col, p.row.y) == (i // nt, g.tops[i % nt]))
x = g.cols[p.row.col][0] + 9 * k
m = bm[p.row.y : p.row.y + 8 * k, x : p.name.x1]
print("k", k, "x_text", x, "name.x0", p.name.x0, "spans (rel):", [(a / k, b / k) for a, b in runs_of(m.any(axis=0))][:8])
for r in m[:, : 12 * k : max(1, k // 2)]:
    print("".join("#" if v else "." for v in r))
