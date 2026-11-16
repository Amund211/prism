"""c_time.py <module>: time match() alone on cached row features (1 process)"""

import importlib
import sys
import time

from c_feats import cached_feats
from data import image, label, train_names

mod = importlib.import_module(sys.argv[1])
ts = []
for n in train_names()[:: int(sys.argv[2]) if len(sys.argv) > 2 else 4]:
    rows = cached_feats(n, image)
    known = list(label(n)["known"])
    t = time.perf_counter()
    mod.match(rows, known)
    ts.append(time.perf_counter() - t)
ts.sort()
print(f"{sys.argv[1]} match ms median {1000 * ts[len(ts) // 2]:.0f} p90 {1000 * ts[int(len(ts) * 0.9)]:.0f} max {1000 * ts[-1]:.0f}")
