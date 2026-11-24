"""grid3_bench.py [sub]: grid3 row count vs labels per train image, and time."""

import sys
import time
from collections import Counter

from data import image, label, train_names
from grid3 import find_grid

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    c = Counter()
    ts = []
    for n in train_names():
        if only not in n:
            continue
        rgb = image(n)
        lab = label(n)
        want = len(lab["rows"]) + len(lab["npcs"])
        t = time.perf_counter()
        g = find_grid(rgb)
        ts.append(time.perf_counter() - t)
        got = len(g.tops) if g else 0
        gs = lab["setup"]["gui_scale"]
        ncol = len(g.cols) if g else 0
        ok = (got * ncol >= want and got * (ncol - 1) < want) if ncol > 1 else got == want
        grp = "lunar" if "lunar" in n else "notab" if want == 0 else "cells"
        c[grp] += 1
        c[grp + "_ok"] += ok
        c[grp + "_rows"] += want
        c[grp + "_rows_ok"] += want if ok else 0
        if not ok or (g and g.k != gs) or only:
            print(f"{'OK ' if ok else 'BAD'} {n:68s} want {want:2d} got {got:2d} gs {gs} k {g.k if g else 0} weak {g.weak if g else None}"
                  f" cols {g.cols if g else None} y0 {g.tops[0] if g else None} ov {lab.get('overlay')}")
    ts.sort()
    print(sorted(c.items()), "ms median", round(1000 * ts[len(ts) // 2]), "max", round(1000 * ts[-1]))
