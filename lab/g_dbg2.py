"""g_dbg2.py <image> <font_id>: width fit and costs for one font."""

import sys

import numpy as np

from common import parse
from data import image, label
from g_bank import bank, ink_width, render
from g_match import cost_matrix, regions_of, width_scores

n, fid = sys.argv[1], sys.argv[2]
lab = label(n)
rgb = image(n)
known = list(lab["known"])
truth = {r["name"]: r["team"] for r in lab["rows"]}
tab, prows = parse(rgb)
k = tab.k
regions = regions_of(rgb, prows, k)
fonts = [f for f in bank() if f.fid == fid]
print([f.key for f in fonts], width_scores(regions, known, fonts, k))
for f in fonts:
    c = cost_matrix(regions, known, f, k)
    for i, r in enumerate(regions[:6]):
        j = int(np.argmin(c[i]))
        print(r.prow.row.y, f"w{(r.x1 - r.x0) / k:.2f}", known[j], round(c[i, j], 2), [
            (nm, round(ink_width(f, nm), 2)) for nm in known if abs(ink_width(f, nm) - (r.x1 - r.x0) / k) < 4
        ][:3])
r = regions[0]
f = fonts[0]
best = min(known, key=lambda nm: abs(ink_width(f, nm) - (r.x1 - r.x0) / k))
t = render(f, best, k)
print(best, t.shape, r.mask.shape)
for a, b in zip(r.mask, t):
    print("".join("#" if x else "." for x in a[:70]), " ", "".join("#" if x else "." for x in b[:70]))
