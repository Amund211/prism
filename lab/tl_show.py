"""tl_show.py <module> [key ...]: list the given keys (default extra, near, miss) per image from results/tl"""

import json
import sys
from collections import Counter
from pathlib import Path

r = json.loads((Path(__file__).parent / f"results/tl/{sys.argv[1]}.json").read_text())
keys = sys.argv[2:] or ["extra", "near", "miss"]
cnt = Counter()
for n, o in sorted(r["images"].items()):
    bad = {k: o[k] for k in keys if o.get(k)}
    for k, v in bad.items():
        cnt[k] += len(v)
    if bad:
        print(n, json.dumps(bad))
print(dict(cnt))
