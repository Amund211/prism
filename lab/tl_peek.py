"""tl_peek.py substr [n]: cached reads (name crop | row crop) of matching images"""

import pickle
import sys
from pathlib import Path

from data import label

cache = pickle.loads((Path(__file__).parent / "results/tl/cache.pkl").read_bytes())
n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
for name in [k for k in sorted(cache) if sys.argv[1] in k][:n]:
    img = cache[name]
    print(name, img["finder"], "team rows", img["n_team"], "labels", [r["name"] for r in label(name)["rows"]])
    for r in img["regions"]:
        c = min(r["name"][1], default=0)
        print(f"  y{r['y']:5d} {str(r['team']):7s} L{int(r['letter'])} {r['name'][0]!r:22s} c{c:.2f} | {r['row'][0]!r}")
