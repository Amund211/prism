"""tl_crops.py out.png substr...: stack the whole-row CRNN crops of the
first image matching each substr (x3 for viewing)"""

import sys

import cv2
import numpy as np

from data import image, train_names
from g_match import regions_of
from i4_synth import norm_crop
from tl_front import front

rows = []
for s in sys.argv[2:]:
    n = next(x for x in train_names() if s in x)
    rgb = image(n)
    _, tab, prows = front(rgb)
    k = tab.k
    for r in regions_of(rgb, prows, k)[:6]:
        c = norm_crop(rgb, r.prow.row.y, r.prow.row.x0, r.prow.row.x1, k)
        rows.append(c)
W = max(c.shape[1] for c in rows)
img = np.vstack([np.pad(c, ((0, 2), (0, W - c.shape[1]), (0, 0))) for c in rows])
img = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
cv2.imwrite(sys.argv[1], cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
