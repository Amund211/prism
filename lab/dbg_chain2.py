import sys

from data import image
from rows import _comps, _extent, _ladders
from textmask import Shadow

n, k = sys.argv[1], int(sys.argv[2])
m = Shadow(image(n)).mask(k)
boxes = _comps(m, k)
chains = sorted(_ladders(boxes, k), key=lambda c: -c.real)
print("ext", _extent(boxes, chains[0], k, chains))
for c in chains[:8]:
    x1 = (c.bx[:, 0] + c.bx[:, 2]).tolist()
    print(c.real, c.lo, c.hi, "x1", x1)
