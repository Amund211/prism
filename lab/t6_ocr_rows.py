"""T6: off-the-shelf OCR (RapidOCR, PP-OCR rec over ONNX) on whole row crops,
as a B-style reader: team from the read letter (else the parse colour),
name = read minus letter and health. Train split. Prints a tbench summary."""

import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor

os.environ.setdefault("OMP_NUM_THREADS", "1")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from data import image, label, train_names  # noqa: E402
from e2_rapidocr import engine  # noqa: E402
from g_match import regions_of  # noqa: E402
from i4_synth import norm_crop  # noqa: E402
from rowparse import LETTER  # noqa: E402
from tbench import score, summarize  # noqa: E402
from tl_front import clean, front, valid  # noqa: E402

BY_LETTER = {v: k for k, v in LETTER.items()}
SCALE = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def read_row(crop):
    big = cv2.resize(crop, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_NEAREST)
    r = engine()(big, use_det=False, use_cls=False, use_rec=True)
    return " ".join(r.txts or ())


def one(name):
    import time

    rgb = image(name)
    t = time.perf_counter()
    _, tab, prows = front(rgb)
    reads = []
    if tab is not None and sum(1 for p in prows if p.team) >= 3:
        for g in regions_of(rgb, prows, tab.k):
            txt = read_row(norm_crop(rgb, g.prow.row.y, g.prow.row.x0, g.prow.row.x1, tab.k))
            w = txt.strip().split()
            team = None
            if len(w) > 1 and w[0] in BY_LETTER:
                team, w = BY_LETTER[w[0]], w[1:]
            if len(w) > 1 and w[-1].isdigit():
                w = w[:-1]
            n = clean(" ".join(w))
            team = team or g.prow.team
            if valid(n):
                reads.append((n, team))
    return name, (score(label(name), reads), time.perf_counter() - t)


def main():
    with ProcessPoolExecutor(4, mp_context=multiprocessing.get_context("fork")) as ex:
        res = dict(ex.map(one, train_names()))
    s = summarize(res)
    print(f"T6 RapidOCR rows x{SCALE}:", s)


if __name__ == "__main__":
    main()
