import sys

from PIL import Image

from data import image
from rows import _comps, _ladders
from textmask import shadow_mask

SCRATCH = "/tmp/claude-1000/-home-amund-git-overlay/e8ae7acd-5312-49fd-afc3-562a24ca66d5/scratchpad"
n, k = sys.argv[1], int(sys.argv[2])
rgb = image(n)
m = shadow_mask(rgb, k)
boxes = _comps(m, k)
for c in sorted(_ladders(boxes, k), key=lambda c: -c.real)[:5]:
    print(c.real, c.lo, c.hi, c.tops)
if len(sys.argv) > 3:
    x0, y0, x1, y1 = map(int, sys.argv[3:7])
    Image.fromarray(m[y0:y1, x0:x1]).resize(((x1 - x0) * 2, (y1 - y0) * 2)).save(f"{SCRATCH}/mask.png")
