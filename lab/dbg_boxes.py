"""dbg_boxes.py <name> <k> <y0> <y1>: word boxes (x, y, w, h) with top in [y0, y1)"""

import sys

from data import image
from rows import _comps
from textmask import Shadow

n, k, y0, y1 = sys.argv[1], *map(int, sys.argv[2:5])
m = Shadow(image(n)).mask(k)
for b in _comps(m, k):
    if y0 <= b[1] < y1 or (b[1] < y0 and b[1] + b[3] > y0):
        print(b.tolist())
