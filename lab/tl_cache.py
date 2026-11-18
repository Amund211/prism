"""tl_cache.py [-j N]: per train image, per name region: CRNN reads of the
name crop and of the whole row (text start .. row end), with per-char
confidence. Writes results/tl/cache.pkl. Used by tl_sweep.py."""

import argparse
import multiprocessing
import os
import pickle
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402

from data import image, label, train_names  # noqa: E402
from g_match import regions_of  # noqa: E402
from i4_rec import logits  # noqa: E402
from i4_synth import CHARS, norm_crop  # noqa: E402
from tl_front import front  # noqa: E402

OUT = Path(__file__).parent / f"results/tl/cache{os.environ.get('TL_CACHE', '')}.pkl"


def decode_conf(lp: np.ndarray) -> tuple[str, list[float]]:
    """Greedy CTC read and the prob of each emitted char (max over its run)"""
    best = lp.argmax(0)
    p = np.exp(lp.max(0))
    text, conf = [], []
    prev = -1
    for t, b in enumerate(best):
        if b != prev and b > 0:
            text.append(CHARS[b - 1])
            conf.append(float(p[t]))
        elif b == prev and b > 0:
            conf[-1] = max(conf[-1], float(p[t]))
        prev = b
    return "".join(text), conf


MODEL = os.environ.get("TL_MODEL", "full")


def mask_crop(m: np.ndarray, k: int, scale: int = 5, pad: int = 8) -> np.ndarray:
    """Region text mask -> black on white, font px x scale (as e_ocrcommon.name_crop)"""
    m = m[::k, ::k] if k > 1 else m
    m = m.repeat(scale, axis=0).repeat(scale, axis=1)
    out = np.full((m.shape[0] + 2 * pad, m.shape[1] + 2 * pad), 255, np.uint8)
    out[pad : pad + m.shape[0], pad : pad + m.shape[1]][m] = 0
    return out


def read(crops, model):
    return [decode_conf(lp) for lp in logits(crops, model)]


def one(name: str):
    rgb = image(name)
    t = time.perf_counter()
    finder, tab, prows = front(rgb)
    out = []
    if tab is not None:
        k = tab.k
        regions = regions_of(rgb, prows, k)
        model = MODEL
        if model == "loo":
            from i4_rec import loo_model

            # TL_LOO_PREFIX "c2/mix_" -> c2/mix_loo0..2
            model = os.environ.get("TL_LOO_PREFIX", "") + loo_model(rgb, tab, prows, list(label(name)["known"]))
        names = read([norm_crop(rgb, r.prow.row.y, r.x0, r.x1, k) for r in regions], model)
        rows = read([norm_crop(rgb, r.prow.row.y, r.prow.row.x0, r.prow.row.x1, k) for r in regions], model)
        ocr = [None] * len(regions)
        if os.environ.get("TL_OCR"):
            from e2_rapidocr import ocr as rapid

            ocr = [rapid(mask_crop(r.mask, k)) for r in regions]
        for r, nm, rw, oc in zip(regions, names, rows, ocr):
            p = r.prow
            out.append({
                "y": p.row.y, "col": p.row.col, "x0": r.x0, "rx0": p.row.x0, "k": k,
                "team": p.team, "letter": p.letter is not None,
                "name": nm, "row": rw, "ocr": oc,
            })
    return name, {"finder": finder, "regions": out, "n_team": sum(1 for p in prows if p.team),
                  "ms": 1000 * (time.perf_counter() - t)}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("-j", type=int, default=4)
    j = a.parse_args().j
    with ProcessPoolExecutor(j, mp_context=multiprocessing.get_context("fork")) as ex:
        res = dict(ex.map(one, train_names()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(pickle.dumps(res))
    print(len(res), "images")


if __name__ == "__main__":
    main()
