"""Team-row ceiling of the cached extract (team multiset vs labels), and the
wrong / unknown names of a tuned module at given thresholds."""

import pickle
import sys
from collections import Counter
from pathlib import Path

from bench import outcome
from common import assign
from data import label

mod, mc, mg = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
data = pickle.loads((Path(__file__).parent / "results" / f"tune_{mod}.pkl").read_bytes())
ceil = 0
for n, teams, names, C, _ in data:
    lab = label(n)
    want = Counter(r["team"] for r in lab["rows"] if r["team"])
    ceil += sum((Counter(t for t in teams if t) & want).values())
    got = {}
    if C is not None and C.size:
        for i, j in assign(C, mc, mg):
            if teams[i]:
                got[names[j]] = teams[i]
    o = outcome(lab, got)
    bad = {k: o[k] for k in ("wrong", "npc", "extra") if o[k]}
    if bad:
        print("BAD", n, bad)
    if len(sys.argv) > 4 and o["unknown"]:
        print("unk", n, len(o["unknown"]), "of", len(lab["rows"]))
print("team-row ceiling", ceil)
