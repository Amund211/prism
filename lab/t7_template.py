"""T7: letter-pattern (template) reader. Name-region mask -> glyph runs (split
at empty columns; DP split of touching glyphs) -> best glyph template of one
font from the bank. Font per image: best mean match on its first regions.
Team: parse colour. Train split; prints a tbench summary.
Usage: t7_template.py [N_FONT_ROWS]"""

import multiprocessing
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from functools import cache

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402

from data import image, label, train_names  # noqa: E402
from g_bank import _glyph, bank  # noqa: E402
from g_match import regions_of  # noqa: E402
from i4_synth import NAME_CHARS  # noqa: E402
from tbench import score, summarize  # noqa: E402
from tl_front import front, valid  # noqa: E402

N_FONT_ROWS = int(sys.argv[1]) if len(sys.argv) > 1 else 4


@cache
def templates(fi: int, k: int):
    """[(char, bool 8k x w)] of font fi at scale k, blank columns cut"""
    f = bank()[fi]
    out = []
    for c in NAME_CHARS:
        g = _glyph(f, ord(c), k, 0.0)
        cols = np.flatnonzero(g.any(0))
        if len(cols):
            out.append((c, g[:, cols[0] : cols[-1] + 1]))
    return out


def match(seg: np.ndarray, tmpl, k: int):
    """(cost, char): best template; cost = mismatched px / union, dy in -k..k"""
    best = (1.0, "?")
    h, w = seg.shape
    for c, t in tmpl:
        if abs(t.shape[1] - w) > k:
            continue
        W = max(w, t.shape[1])
        a = np.zeros((h, W), bool)
        a[:, :w] = seg
        for dy in range(-k, k + 1):
            b = np.zeros((h, W), bool)
            if dy >= 0:
                b[dy:, : t.shape[1]] = t[: h - dy]
            else:
                b[:dy, : t.shape[1]] = t[-dy:]
            u = (a | b).sum()
            cost = (a ^ b).sum() / u if u else 1.0
            if cost < best[0]:
                best = (cost, c)
    return best


def read_mask(m: np.ndarray, tmpl, k: int):
    """(text, mean cost) of a name mask"""
    cols = m.any(0)
    runs, x = [], 0
    while x < len(cols):
        if cols[x]:
            x0 = x
            while x < len(cols) and cols[x]:
                x += 1
            runs.append(m[:, x0:x])
        x += 1
    widths = sorted({t.shape[1] for _, t in tmpl})
    maxw = max(widths) + k
    text, costs = [], []
    for r in runs:
        if r.shape[1] <= maxw:
            c, ch = match(r, tmpl, k)
            text.append(ch)
            costs.append(c)
            continue
        # touching glyphs: DP over cut points
        W = r.shape[1]
        dp = [(0.0, [])] + [(1e9, [])] * W
        for x1 in range(1, W + 1):
            for wd in widths:
                for d in (0, -k, k):
                    x0 = x1 - wd - d
                    if x0 < 0 or x0 >= x1 or dp[x0][0] >= 1e9:
                        continue
                    c, ch = match(r[:, x0:x1], tmpl, k)
                    if dp[x0][0] + c < dp[x1][0]:
                        dp[x1] = (dp[x0][0] + c, dp[x0][1] + [(ch, c)])
        for ch, c in dp[W][1]:
            text.append(ch)
            costs.append(c)
    return "".join(text), (float(np.mean(costs)) if costs else 1.0)


def one(name):
    rgb = image(name)
    t = time.perf_counter()
    _, tab, prows = front(rgb)
    reads = []
    if tab is not None and sum(1 for p in prows if p.team) >= 3:
        k = tab.k
        regs = regions_of(rgb, prows, k)
        fonts = list(range(len(bank())))
        probe = regs[:N_FONT_ROWS]
        fi = min(fonts, key=lambda i: np.mean([read_mask(r.mask, templates(i, k), k)[1] for r in probe]) if probe else 0)
        for r in regs:
            n, c = read_mask(r.mask, templates(fi, k), k)
            if valid(n):
                reads.append((n, r.prow.team))
    return name, (score(label(name), reads), time.perf_counter() - t)


def main():
    with ProcessPoolExecutor(4, mp_context=multiprocessing.get_context("fork")) as ex:
        res = dict(ex.map(one, train_names()))
    print(f"T7 template (font from {N_FONT_ROWS} rows):", summarize(res))


if __name__ == "__main__":
    main()
