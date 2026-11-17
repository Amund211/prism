"""ping_stage.py <substr>: per Lunar ping row, is there a name word / team?"""
import sys
from collections import Counter

import ping_grid
from data import image, label, train_names
from j3_slot import grid_parse

c = Counter()
for n in train_names():
    if sys.argv[1] not in n or "lunar" not in n:
        continue
    lab = label(n)
    want = len(lab["rows"]) + len(lab["npcs"])
    g = ping_grid.find_ping(image(n))
    if g is None:
        c["no_rows"] += want
        print(n, "no rows")
        continue
    _, tab, prows = grid_parse(image(n), slot=False, g=g)
    nn = sum(1 for p in prows if p.name is not None)
    nt = sum(1 for p in prows if p.team)
    c["rows"] += len(g.tops)
    c["name"] += nn
    c["team"] += nt
    print(f"{n:62s} want {want:2d} rows {len(g.tops):2d} parsed {len(prows):2d} name {nn:2d} team {nt:2d}")
print(dict(c))
