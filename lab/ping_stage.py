"""ping_stage.py <substr>: per Lunar ping row, name word / team; for rows
with a name and no team, the letter slot's reason (j3_slot.slot_team)"""
import sys
from collections import Counter

import ping_grid
from data import image, label, train_names
from j3_slot import grid_parse, slot_team
from lunar_mask import lunar_mask

c = Counter()
for n in train_names():
    if sys.argv[1] not in n or "lunar" not in n:
        continue
    lab = label(n)
    want = len(lab["rows"]) + len(lab["npcs"])
    nulls = sum(1 for r in lab["rows"] if r.get("team") is None) + len(lab["npcs"])
    rgb = image(n)
    g = ping_grid.find_ping(rgb)
    if g is None:
        c["no_rows"] += want
        print(n, "no rows")
        continue
    _, tab, prows = grid_parse(rgb, g=g, maskfn=lunar_mask, icon=True)
    bm = lunar_mask(rgb, g)
    k = g.k
    whys = Counter()
    for p in prows:
        if p.name is not None and p.team is None:
            xt = g.cols[0][0] + 9 * k
            _, w1 = slot_team(rgb, bm, p, xt, k)
            _, w2 = slot_team(rgb, bm, p, xt + 9 * k, k)
            whys[f"{w1}/{w2}"] += 1
    nn = sum(1 for p in prows if p.name is not None)
    nt = sum(1 for p in prows if p.team)
    c["rows"] += len(g.tops)
    c["name"] += nn
    c["team"] += nt
    c["label_no_team"] += nulls
    print(f"{n:62s} want {want:2d} rows {len(g.tops):2d} name {nn:2d} team {nt:2d} label-null {nulls:2d} {dict(whys)}")
print(dict(c))
