"""e_loss.py <tag>: where do labeled team rows get lost (cached OCR)?"""

import json
import sys
from collections import Counter
from pathlib import Path

from data import label
from e_ocrcommon import sim

res = json.loads((Path(__file__).parent / "results" / f"ocr_{sys.argv[1]}.json").read_text())
c = Counter()
by_font: dict[str, Counter] = {}
for n, v in res.items():
    lab = label(n)
    f = by_font.setdefault(lab["setup"]["font"] or "none", Counter())
    for r in lab["rows"]:
        if not r["team"]:
            continue
        sims = [(sim(t, r["name"]), tm) for t, tm in zip(v["texts"], v["teams"])]
        best = max(sims, default=(0, None), key=lambda s: s[0])
        if best[0] < 0.6:
            key = "no text"
        elif best[1] is None:
            key = "text, no team"
        elif best[1] != r["team"]:
            key = "text, wrong team"
        else:
            key = "ok"
        c[key] += 1
        f[key] += 1
print(dict(c))
for font, cc in sorted(by_font.items()):
    print(f"  {font:32s} {dict(cc)}")
