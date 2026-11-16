"""e_loss2.py <tag>: loss sources for row-band OCR (e2c)"""

import json
import sys
from collections import Counter
from pathlib import Path

from data import label
from e2c_rowband import score

res = json.loads((Path(__file__).parent / "results" / f"ocr_{sys.argv[1]}.json").read_text())
c = Counter()
by: dict[str, Counter] = {}
ex = []
for n, v in res.items():
    lab = label(n)
    f = by.setdefault(lab["setup"]["font"] or "none", Counter())
    for r in lab["rows"]:
        if not r["team"]:
            continue
        sc = [(score(r["name"], t), t, col) for t, col in zip(v["texts"], v["teams"])]
        (s, letter), t, col = max(sc, default=((0, None), "", None), key=lambda x: x[0][0])
        if s < 0.7:
            key = "no text"
        elif letter is None:
            key = "no letter"
            ex.append((r["name"], r["team"], t))
        elif letter != r["team"]:
            key = "wrong letter"
            ex.append((r["name"], r["team"], t))
        elif col is not None and col != letter:
            key = "colour disagrees"
            ex.append((r["name"], r["team"], t, col))
        else:
            key = "ok"
        c[key] += 1
        f[key] += 1
print(dict(c))
for font, cc in sorted(by.items()):
    print(f"  {font:32s} {dict(cc)}")
for e in ex[:40]:
    print(e)
