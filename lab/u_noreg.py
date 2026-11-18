"""u_noreg.py: per image, labeled rows vs regions, finder; images with lost rows"""

import pickle
from pathlib import Path

from data import label

CACHE = Path(__file__).parent / "results/tl/ucache.pkl"
cache = pickle.loads(CACHE.read_bytes())
for n, img in sorted(cache.items()):
    lab = label(n)
    nr, ng = len(lab["rows"]), len(img["regions"])
    if nr and ng < nr:
        print(f"{n:60s} {img['finder']:5s} rows {nr:3d} regions {ng:3d} team {img['n_team']:3d} "
              f"gs {lab['setup'].get('gui_scale')} {lab['setup'].get('client')}")
