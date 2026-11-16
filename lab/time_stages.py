"""1-process timing of stage 1+2 (find_tab + parse) on a fixed subset."""

import os
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "1")

import cProfile  # noqa: E402
import pstats  # noqa: E402

from common import parse  # noqa: E402
from data import image, train_names  # noqa: E402
from rows import find_tab  # noqa: E402

names = train_names()[:: max(1, len(train_names()) // 20)][:20]
imgs = [image(n) for n in names]
prof = "--prof" in sys.argv
pr = cProfile.Profile() if prof else None
t_tab, t_all = [], []
for im in imgs:
    if pr:
        pr.enable()
    t = time.perf_counter()
    tab = find_tab(im)
    t1 = time.perf_counter()
    parse(im, tab)
    t2 = time.perf_counter()
    if pr:
        pr.disable()
    t_tab.append(t1 - t)
    t_all.append(t2 - t)
t_tab.sort()
t_all.sort()
print(f"find_tab median {1000*t_tab[10]:.0f} ms max {1000*t_tab[-1]:.0f}; tab+parse median {1000*t_all[10]:.0f} ms max {1000*t_all[-1]:.0f}")
if pr:
    pstats.Stats(pr).sort_stats("cumulative").print_stats(18)
