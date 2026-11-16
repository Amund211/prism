"""c5 costs == c1v_q costs on some cached images"""

import numpy as np

import c1v_q
import c5_fast
from c_feats import cached_feats
from data import image, label, train_names

worst = 0.0
for n in train_names()[::10]:
    rows = cached_feats(n, image)
    known = list(label(n)["known"])
    if not rows or not known:
        continue
    a = c1v_q.costs(rows, known)
    b = c5_fast.costs(rows, known)
    worst = max(worst, float(np.abs(a - b).max()))
print("max abs diff", worst)
