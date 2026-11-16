import sys

import font
from common import parse
from data import image, label

n = sys.argv[1]
lab = label(n)
tab, prows = parse(image(n))
print("k", tab.k, "rows", len(prows))
for p in prows:
    k = p.row.k
    ws = [(w.x0, round((w.x1 - w.x0) / k, 1), w.color, len(w.spans)) for w in p.words]
    print(p.row.y, p.row.col, p.team, ws)
for r in lab["rows"]:
    print(r["name"], r["team"], font.width(r["name"]))
