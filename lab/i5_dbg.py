"""i5: debug aux tab for one image"""

import sys
from collections import Counter

import numpy as np

import i5_rows
from data import image, train_names
from rows import find_tab

n = next(m for m in train_names() if sys.argv[1] in m)
rgb = image(n)
t = find_tab(rgb)
print(n, "k", t.k, "real", t.real, [(r.y, r.x0, r.x1) for r in t.rows][:5])
reg = rgb[t.rows[0].y : t.rows[0].y + 8 * t.k, max(0, t.rows[0].x0 - 140 * t.k) : t.rows[0].x0]
px = reg.reshape(-1, 3)
c = Counter(map(tuple, px[px.max(axis=1) >= 120].tolist()))
print("bright colours left of row 0:", c.most_common(12))
print("pal px:", int(i5_rows.palette_mask(reg).sum()))
print("overlay:", i5_rows.overlay_params(rgb[t.rows[0].y : t.rows[-1].y + 8 * t.k, max(0, t.rows[0].x0 - 140 * t.k) : t.rows[0].x1], t.k))
t2, _ = i5_rows.find_tab_i5(rgb, tab=t)
print("aux real", t2.real, "same" if t2 is t else "", [(r.y, r.x0, r.x1) for r in t2.rows][:5])
t2, rgb2 = i5_rows.find_tab_i5(rgb, tab=t)
_, pr = i5_rows._parse_on(rgb2, t2, True, True)
for p in pr[:6]:
    print(p.row.y, p.team, p.letter and (p.letter.x0, p.letter.x1), p.name and (p.name.x0, p.name.x1, p.name.color),
          [(w.x0, w.x1, len(w.spans), w.color) for w in p.words])
