"""i2_dbg.py <substr> [n]: run i2_spot on train images, print outcome + time."""

import sys
import time

import i2_spot
from bench import outcome
from data import image, label, train_names

names = [n for n in train_names() if sys.argv[1] in n][: int(sys.argv[2]) if len(sys.argv) > 2 else 3]
for n in names:
    lab = label(n)
    rgb = image(n)
    t = time.perf_counter()
    got = i2_spot.read_teams(rgb, list(lab["known"]))
    dt = time.perf_counter() - t
    o = outcome(lab, got)
    print(n, f"{dt*1000:.0f}ms", {k: len(v) for k, v in o.items()}, o["wrong"], o["npc"], o["extra"])
