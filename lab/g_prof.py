"""Time split: parse vs regions vs width prune vs IoU (single process)."""

import time

import numpy as np

from common import parse
from data import image, label, train_names
from g_bank import bank
from g_match import cost_matrix, regions_of, width_scores

bank()
T = np.zeros(4)
names = train_names()[::8]
for n in names:
    lab = label(n)
    rgb = image(n)
    known = list(lab["known"])
    t0 = time.perf_counter()
    tab, prows = parse(rgb)
    t1 = time.perf_counter()
    if tab is None or not known:
        T[0] += t1 - t0
        continue
    k = tab.k
    regions = regions_of(rgb, prows, k)
    t2 = time.perf_counter()
    if not regions:
        continue
    fonts = bank()
    ws = width_scores(regions, known, fonts, k)
    t3 = time.perf_counter()
    cand = [fonts[i] for i in np.argsort(ws)[:6]]
    [cost_matrix(regions, known, f, k) for f in cand]
    t4 = time.perf_counter()
    T += [t1 - t0, t2 - t1, t3 - t2, t4 - t3]
print(len(names), "images, mean ms: parse %.0f regions %.0f widths %.0f iou %.0f" % tuple(1000 * T / len(names)))
