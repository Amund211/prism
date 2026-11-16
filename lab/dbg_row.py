"""dbg_row.py <name> <row y>: spans, text colours and word split of one row"""

import sys

import numpy as np

from data import image
from rowparse import text_colors, words
from rows import find_tab

n, y = sys.argv[1], int(sys.argv[2])
rgb = image(n)
tab = find_tab(rgb)
r = next(r for r in tab.rows if r.y == y)
k = r.k
print("row", r.y, r.x0, r.x1, "spans", r.runs)
band = rgb[r.y : r.y + 8 * k, r.x0 : r.x1].astype(np.int16)
sm = tab.mask[r.y : r.y + 8 * k, r.x0 : r.x1]
print("text colours", text_colors(band[sm], max(3, 2 * k * k)).tolist())
for w in words(rgb, tab.mask, r):
    print("word", w.x0, w.x1, w.color, len(w.spans))
for row in sm:
    print("".join("#" if v else "." for v in row[:200]))
