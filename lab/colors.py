"""colors.py <name> x0 y0 x1 y1: most common colors and shadow check"""

import sys
from collections import Counter

import numpy as np

from data import image

name, x0, y0, x1, y1 = sys.argv[1], *map(int, sys.argv[2:6])
s = int(sys.argv[6]) if len(sys.argv) > 6 else 2
img = image(name).astype(int)
c = img[y0:y1, x0:x1]
cnt = Counter(map(tuple, c.reshape(-1, 3)))
for col, n in cnt.most_common(25):
    print(col, n)
# shadow: pixel at (+s,+s) is col//4
sub = img[y0 : y1 + s, x0 : x1 + s]
a = sub[:-s, :-s]
b = sub[s:, s:]
bright = a.max(axis=2) > 120
ok = bright & (np.abs(b - a // 4).max(axis=2) <= 2)
print("bright", bright.sum(), "with exact shadow", ok.sum())
