"""I4 debug: real row crops of train images + CRNN reads. i4_dbg.py MODEL SUBSTR [N]"""

import sys

import cv2
import numpy as np

from common import parse
from data import image, label, train_names
from g_match import regions_of
from i4_rec import OUT, read_crops
from i4_synth import norm_crop

model, sub = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
rows = []
for name in [x for x in train_names() if sub in x][:n]:
    rgb = image(name)
    tab, prows = parse(rgb)
    if tab is None:
        continue
    regs = regions_of(rgb, prows, tab.k)
    crops = [norm_crop(rgb, r.prow.row.y, r.x0, r.x1, tab.k) for r in regs]
    print(name, "k", tab.k, "known", label(name)["known"][:20])
    print("   reads", read_crops(crops, model))
    rows += [cv2.resize(c, (240, 20)) for c in crops]
if rows:
    cv2.imwrite(str(OUT / "real_preview.png"), cv2.cvtColor(np.vstack(rows[:60]), cv2.COLOR_RGB2BGR))
