"""budget.py [result]: error budget over all train rows from an oracle result
(default results/oracle_slot.json). Rows and % of all rows, plain and weighted."""

import json
import sys
from collections import Counter
from pathlib import Path

from data import label, load_weights

name = sys.argv[1] if len(sys.argv) > 1 else "oracle_slot"
res = json.loads((Path(__file__).parent / f"results/{name}.json").read_text())
W = load_weights()
c, wc = Counter(), Counter()
font = {}
for n, r in res.items():
    w = W[n]
    o = r["s0"]
    if r["why"] is None:
        for st in r["stages"].values():
            c[st] += 1
            wc[st] += w
            if st != "ok":
                f = (label(n)["setup"]["font"] or "none").removeprefix("pack:").split("-")[0]
                font.setdefault(st, Counter())[f] += 1
    else:
        nok = len(o["correct"])
        lost = len(o["wrong"]) + len(o["unknown"])
        c["ok"] += nok
        wc["ok"] += w * nok
        c[f"img:{r['why']}"] += lost
        wc[f"img:{r['why']}"] += w * lost
tot, wtot = sum(c.values()), sum(wc.values())
print(f"{'loss':16s} {'rows':>5s} {'%':>6s} {'w %':>6s}  top fonts")
for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
    top = ", ".join(f"{f} {m}" for f, m in font.get(k, Counter()).most_common(4))
    print(f"{k:16s} {v:5d} {100 * v / tot:6.1f} {100 * wc[k] / wtot:6.1f}  {top}")
