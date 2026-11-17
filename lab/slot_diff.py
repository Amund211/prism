"""slot_diff.py <image>: rows whose team comes from the letter slot"""

import sys

from bgmask import bg_mask
from common import team_of
from data import image
from j3_slot import grid_parse, slot_team

rgb = image(sys.argv[1])
g, tab, prows = grid_parse(rgb, slot=False)
bm = bg_mask(rgb, g)
print("k", g.k, "weak", g.weak, "tops", len(g.tops), "cols", g.cols)
for p in prows:
    if p.name is None or p.team is not None:
        continue
    t, why = slot_team(rgb, bm, p, g.cols[p.row.col][0] + 9 * g.k, g.k)
    print(p.row.y, p.name.x0, "name col", p.name.color, "shadow", p.name.shadow, "team_of(name)", team_of(p.name), "->", t, why)
