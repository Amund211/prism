"""g_dbg3.py <image> <font_id> <row index> <name>: full masks and IoU."""

import sys

import numpy as np

from common import parse
from data import image
from g_bank import bank, iou, render
from g_match import regions_of

n, fid, ri, nm = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
rgb = image(n)
tab, prows = parse(rgb)
k = tab.k
r = regions_of(rgb, prows, k)[ri]
f = next(f for f in bank() if f.fid == fid)
t = render(f, nm, k)
print(r.mask.shape, t.shape, iou(r.mask, t))
w = max(r.mask.shape[1], t.shape[1])
for i in range(max(r.mask.shape[0], t.shape[0])):
    a = r.mask[i] if i < r.mask.shape[0] else np.zeros(0, bool)
    b = t[i] if i < t.shape[0] else np.zeros(0, bool)
    print("".join("#" if x else "." for x in a[::3]).ljust(w // 3), "|", "".join("#" if x else "." for x in b[::3]))
