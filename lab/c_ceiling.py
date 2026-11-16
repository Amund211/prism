"""c_ceiling.py [module]: upper bound for any name matcher on the cached rows
(per image and team: min(rows read with that team, labeled rows) + no-team
rows), per font; with a module also its result per font."""

import importlib
import sys
from collections import Counter

from bench import outcome
from c_feats import cached_feats
from data import image, label, train_names

mod = importlib.import_module(sys.argv[1]) if len(sys.argv) > 1 else None
by: dict[str, Counter] = {}
for n in train_names():
    lab = label(n)
    rows = cached_feats(n, image)
    got = Counter(r.team for r in rows if r.team)
    want = Counter(r["team"] for r in lab["rows"] if r["team"])
    g = by.setdefault(lab["setup"]["font"] or "none", Counter())
    g["ceil"] += sum((got & want).values()) + sum(1 for r in lab["rows"] if not r["team"])
    g["total"] += len(lab["rows"])
    if mod:
        g["ok"] += len(outcome(lab, mod.match(rows, list(lab["known"])) if rows else {})["correct"])
t = Counter()
for f, g in sorted(by.items()):
    t.update(g)
    print(f"  {f:34s} rows {g['total']:4d} ceiling {100 * g['ceil'] / max(1, g['total']):5.1f} got {100 * g['ok'] / max(1, g['total']):5.1f}")
print(f"ceiling {100 * t['ceil'] / t['total']:.1f} got {100 * t['ok'] / t['total']:.1f}")
