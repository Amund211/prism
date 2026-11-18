"""u_peek.py SUBSTR: labeled rows, known, and region reads of matching images"""

import pickle
import sys
from pathlib import Path

from data import label

cache = pickle.loads((Path(__file__).parent / "results/tl/ucache.pkl").read_bytes())
for n, img in sorted(cache.items()):
    if sys.argv[1] not in n:
        continue
    lab = label(n)
    print(n, img["finder"], "n_team", img["n_team"], "known", len(lab["known"]))
    print("  rows:", [(r["name"], r["team"]) for r in lab["rows"]])
    for r in img["regions"]:
        print("   ", r["team"], repr(r["name"][0]), repr(r["row"][0]))
