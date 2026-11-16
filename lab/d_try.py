"""d_try.py <module> <image>: costs + calib glyph count for one image"""

import importlib
import sys
import time

import numpy as np

from d_core import extract
from data import image, label

mod, n = sys.argv[1], sys.argv[2]
m = importlib.import_module(mod)
lab = label(n)
rgb = image(n)
t = time.perf_counter()
ext = extract(rgb)
print("extract ms", round(1000 * (time.perf_counter() - t)), "k", ext.k, "rows", len(ext.rows))
print("calib chars", "".join(sorted({c for c, _ in ext.calib})))
t = time.perf_counter()
teams, names, C = m.costs(rgb, list(lab["known"]))
print("costs ms", round(1000 * (time.perf_counter() - t)))
truth = {r["name"]: r["team"] for r in lab["rows"]}
np.set_printoptions(precision=2, linewidth=200)
for i, t_ in enumerate(teams):
    j = int(C[i].argmin())
    s = np.sort(C[i])
    print(i, t_, f"{names[j]:18s} {s[0]:.2f} next {s[1] if len(s) > 1 else 9:.2f}", "truth", truth.get(names[j]))
print(m.read_teams(rgb, list(lab["known"])))
