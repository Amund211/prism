"""h5_wrongs.py <result name>: print wrong / npc / extra rows per image."""

import json
import sys
from collections import Counter
from pathlib import Path

r = json.loads((Path(__file__).parent / "results" / f"{sys.argv[1]}.json").read_text())
c = Counter()
for n, o in sorted(r["images"].items()):
    bad = {k: o[k] for k in ("wrong", "npc", "extra") if o[k]}
    if bad:
        print(n, json.dumps(bad))
    for v in o["wrong"].values():
        c[v] += 1
print(c.most_common(12))
