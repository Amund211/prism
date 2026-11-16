"""Shadow.mask must equal the reference shadow_mask."""

import time

import numpy as np

from data import image, train_names
from textmask import Shadow, shadow_mask

for n in train_names()[::40]:
    rgb = image(n)
    t = time.perf_counter()
    s = Shadow(rgb)
    fast = [s.mask(k) for k in range(1, 7)]
    dt = time.perf_counter() - t
    ref = [shadow_mask(rgb, k) for k in range(1, 7)]
    print(n, all(np.array_equal(a, b) for a, b in zip(fast, ref)), f"{dt*1000:.0f} ms for 6 k")
