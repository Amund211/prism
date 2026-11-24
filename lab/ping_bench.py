"""ping_bench.py [sub]: ping_grid row count vs labels per train image (default: lunar), and time."""

import sys
import time
from collections import Counter

from data import image, label, train_names
from ping_grid import find_ping

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else "lunar"
    c = Counter()
    ts = []
    for n in train_names():
        if only not in n:
            continue
        rgb = image(n)
        lab = label(n)
        want = len(lab["rows"]) + len(lab["npcs"])
        t = time.perf_counter()
        g = find_ping(rgb)
        ts.append(time.perf_counter() - t)
        got = len(g.tops) if g else 0
        ok = got == want
        c["n"] += 1
        c["ok"] += ok
        c["rows"] += want
        c["rows_ok"] += want if ok else 0
        print(f"{'OK ' if ok else 'BAD'} {n:68s} want {want:2d} got {got:2d} k {g.k if g else 0}"
              f" cols {g.cols if g else None} y0 {g.tops[0] if g else None}")
    ts.sort()
    print(sorted(c.items()), "ms median", round(1000 * ts[len(ts) // 2]), "max", round(1000 * ts[-1]))
