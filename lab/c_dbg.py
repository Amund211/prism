"""c_dbg.py <module> <image>: per row: runs, top-3 names by cost"""

import importlib
import sys

import numpy as np

from c_feats import cached_feats, name_glyphs
from data import image, label

mod = importlib.import_module(sys.argv[1])
n = sys.argv[2]
lab = label(n)
rows = cached_feats(n, image)
known = list(lab["known"])
cost = mod.costs(rows, known)
for i, r in enumerate(rows):
    order = np.argsort(cost[i])[:3]
    runs = " ".join(f"{g.w:.0f}/{g.top:.0f}{g.bot:.0f}" for g in r.runs)
    best = ", ".join(f"{known[j]} {cost[i, j]:.2f}" for j in order)
    print(f"{r.y:4d} {r.team} w{r.width:.0f} [{runs}] -> {best}")
for row in lab["rows"]:
    gs = " ".join(f"{g.w:.0f}/{g.top:.0f}{g.bot:.0f}" for g in name_glyphs(row["name"]))
    print(row["name"], row["team"], f"[{gs}]")
