"""tl_hybrid.py [policy] [--cache=_loo]: hybrid use. Reads that snap to a
known name are matched (closed set); reads that do not snap are "new"
players. Leave-one-out: drop each labeled row name from known; is it found
as an exact new read? False new = new reads that are not a labeled row."""

import pickle
import sys

from data import label
from i4_rec import cost
from tl_sweep import CACHE, POLICIES, policy

SNAP = 0.34


def new_reads(reads, known):
    return [(n, t) for n, t in reads if not known or min(cost(n, k) for k in known) > SNAP]


def main():
    pol = next((a for a in sys.argv[1:] if not a.startswith("--")), "Q2")
    kw = POLICIES[next(p for p in POLICIES if p.startswith(pol))]
    cache = pickle.loads(CACHE.read_bytes())
    found = tried = false_new = imgs = 0
    team_ok = 0
    by: dict = {}
    for name, img in cache.items():
        lab = label(name)
        if not lab["rows"]:
            continue
        imgs += 1
        reads = policy(img, **kw)
        rows = {r["name"]: r["team"] for r in lab["rows"]}
        known = list(lab["known"])
        bad = [n for n, _ in new_reads(reads, known) if n not in rows]
        if bad and "--show" in sys.argv:
            print("  ", name, bad)
        fn = len(bad)
        false_new += fn
        g = by.setdefault(lab["setup"]["font"], [0, 0])
        g[0] += fn
        g[1] += 1
        for drop in rows:
            tried += 1
            got = dict(new_reads(reads, [k for k in known if k != drop]))
            if drop in got:
                found += 1
                team_ok += got[drop] == rows[drop]
    print(pol, CACHE.name, f"dropped name found exact {100 * found / tried:.1f} % "
          f"(team ok {100 * team_ok / tried:.1f} %), false new reads {false_new} in {imgs} images "
          f"({false_new / imgs:.2f} / image)")
    if "--groups" in sys.argv:
        for f, (n, i) in sorted(by.items()):
            print(f"  {f:34s} false new {n:3d} in {i:3d} images")


if __name__ == "__main__":
    main()
