"""u_cache.py [-j N]: like tl_cache.py, but also keeps the CTC log-probs
(C x T, float16) of the name crop and the row crop, plus shifted name crops
(TTA). TL_MODEL / TL_CACHE as tl_cache. Writes results/tl/ucache{TL_CACHE}.pkl."""

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
from i4_synth import norm_crop  # noqa: E402
from tl_cache import decode_conf  # noqa: E402
from tl_front import front  # noqa: E402

OUT = Path(__file__).parent / f"results/tl/ucache{os.environ.get('TL_CACHE', '')}.pkl"
MODEL = os.environ.get("TL_MODEL", "c2/mix_wide")
# (dx0, dx1, dy) in font px, times k
SHIFTS = [(-1, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, -1)]


def lps(crops, model):
    return [lp.astype(np.float16) for lp in logits(crops, model)]


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

            model = os.environ.get("TL_LOO_PREFIX", "") + loo_model(rgb, tab, prows, list(label(name)["known"]))
        ln = lps([norm_crop(rgb, r.prow.row.y, r.x0, r.x1, k) for r in regions], model)
        lr = lps([norm_crop(rgb, r.prow.row.y, r.prow.row.x0, r.prow.row.x1, k) for r in regions], model)
        tta = [lps([norm_crop(rgb, r.prow.row.y + dy * k, r.x0 + dx0 * k, r.x1 + dx1 * k, k) for r in regions],
                   model) for dx0, dx1, dy in SHIFTS]
        for i, r in enumerate(regions):
            p = r.prow
            out.append({
                "y": p.row.y, "col": p.row.col, "x0": r.x0, "rx0": p.row.x0, "k": k,
                "team": p.team, "letter": p.letter is not None,
                "name": decode_conf(ln[i].astype(np.float32)), "row": decode_conf(lr[i].astype(np.float32)),
                "ocr": None, "lp_name": ln[i], "lp_row": lr[i], "lp_tta": [x[i] for x in tta],
            })
    return name, {"finder": finder, "regions": out, "n_team": sum(1 for p in prows if p.team),
                  "ms": 1000 * (time.perf_counter() - t)}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("-j", type=int, default=2)
    j = a.parse_args().j
    with ProcessPoolExecutor(j, mp_context=multiprocessing.get_context("fork")) as ex:
        res = dict(ex.map(one, train_names()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(pickle.dumps(res))
    print(len(res), "images")


if __name__ == "__main__":
    main()
