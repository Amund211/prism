"""g_dbg.py <image>: chosen fonts, per-row best names and costs."""

import sys

import numpy as np

from common import parse
from data import image, label
from g_bank import bank, ink_width, name_region
from g_match import cost_matrix, regions_of, width_scores

n = sys.argv[1]
lab = label(n)
rgb = image(n)
known = list(lab["known"])
truth = {r["name"]: r["team"] for r in lab["rows"]}
tab, prows = parse(rgb)
k = tab.k
regions = regions_of(rgb, prows, k)
fonts = bank()
ws = width_scores(regions, known, fonts, k)
order = np.argsort(ws)
for i in order[:8]:
    print(f"{fonts[i].key:30s} {fonts[i].family:6s} width-score {ws[i]:.2f}")
f = fonts[order[0]]
c = cost_matrix(regions, known, f, k)
for i, r in enumerate(regions):
    j = np.argsort(c[i])[:2]
    print(
        r.prow.row.y, r.prow.team, f"w{(r.x1 - r.x0) / k:.1f}",
        [(known[x], round(c[i, x], 2), round(ink_width(f, known[x]), 1), truth.get(known[x], "-")) for x in j],
    )
