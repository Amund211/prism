"""u_sizes.py: train image sizes and font scale k, with union / snap score per size"""

import pickle
from collections import defaultdict
from pathlib import Path

from data import image, label
from tbench import score
from u_union import read

cache = pickle.loads((Path(__file__).parent / "results/tl/uvar.pkl").read_bytes())
by = defaultdict(lambda: [0, 0, 0, set()])
for n, img in cache.items():
    lab = label(n)
    h, w = image(n).shape[:2]
    ks = {r["k"] for r in img["regions"]}
    o = score(lab, read(img, list(lab["known"]), "union", "g3", 0.7))
    b = by[f"{w}x{h}"]
    if (w, h) != (1920, 1080):
        print(f"  {w}x{h} {n} rows {len(lab['rows'])} full {len(o['full'])} miss {o['miss']}")
    b[0] += 1
    b[1] += len(lab["rows"])
    b[2] += len(o["full"])
    b[3] |= ks
for s, (ni, nr, nf, ks) in sorted(by.items(), key=lambda x: -x[1][0]):
    print(f"{s:12s} images {ni:3d} rows {nr:4d} union full {100 * nf / max(1, nr):5.1f} k {sorted(ks)}")
