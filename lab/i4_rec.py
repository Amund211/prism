"""I4: CRNN-CTC row reader (ONNX) + lobby matcher."""

import json
import os
import re
from functools import cache
from pathlib import Path

import numpy as np
import onnxruntime as ort
from rapidfuzz.distance import Levenshtein

from common import assign, parse
from g_match import regions_of
from i4_synth import CHARS, norm_crop

OUT = Path(__file__).parent / "results/i4"
MODEL = os.environ.get("I4_MODEL", "full")
MAX_COST, MARGIN = 0.5, 0.12  # i4_sweep.py: margin has no effect; wrong stays 1 up to 0.5


@cache
def session(name: str) -> ort.InferenceSession:
    o = ort.SessionOptions()
    o.intra_op_num_threads = 1
    o.inter_op_num_threads = 1
    # "c2/x" -> results/c2/x.onnx; plain names are i4 models
    path = OUT.parent / f"{name}.onnx" if "/" in name else OUT / f"{name}.onnx"
    return ort.InferenceSession(str(path), o, providers=["CPUExecutionProvider"])


def decode(lg: np.ndarray) -> str:
    best = lg.argmax(0)
    keep = (best != np.concatenate([[-1], best[:-1]])) & (best > 0)
    return "".join(CHARS[b - 1] for b in best[keep])


def read_crops(crops: list[np.ndarray], model: str) -> list[str]:
    s = session(model)
    out = []
    for c in crops:
        x = (c.astype(np.float32) / 255).transpose(2, 0, 1)[None]
        out.append(decode(s.run(None, {"x": x})[0][0]))
    return out


def logits(crops: list[np.ndarray], model: str) -> list[np.ndarray]:
    """Log-softmax C x T per crop"""
    s = session(model)
    out = []
    for c in crops:
        x = (c.astype(np.float32) / 255).transpose(2, 0, 1)[None]
        y = s.run(None, {"x": x})[0][0]
        y = y - y.max(0)
        out.append(y - np.log(np.exp(y).sum(0)))
    return out


def ctc_nll(lp: np.ndarray, names: list[str]) -> np.ndarray:
    """CTC negative log-likelihood of each name (batched over names)"""
    T = lp.shape[1]
    labs = [[CHARS.index(c) + 1 if c in CHARS else 0 for c in n] for n in names]
    S = 2 * max(len(l) for l in labs) + 1
    ext = np.zeros((len(names), S), int)
    valid = np.zeros((len(names), S), bool)
    skip = np.zeros((len(names), S), bool)
    for i, l in enumerate(labs):
        ext[i, 1 : 2 * len(l) : 2] = l
        valid[i, : 2 * len(l) + 1] = True
        for s in range(3, 2 * len(l), 2):
            skip[i, s] = ext[i, s] != ext[i, s - 2]
    ninf = -1e30
    a = np.full((len(names), S), ninf)
    e = lp[:, 0][ext]
    a[:, 0] = e[:, 0]
    a[:, 1] = e[:, 1]
    for t in range(1, T):
        p1 = np.concatenate([np.full((len(names), 1), ninf), a[:, :-1]], 1)
        p2 = np.concatenate([np.full((len(names), 2), ninf), a[:, :-2]], 1)
        p2 = np.where(skip, p2, ninf)
        m = np.maximum(np.maximum(a, p1), p2)
        a = m + np.log(np.exp(a - m) + np.exp(p1 - m) + np.exp(p2 - m)) + lp[:, t][ext]
        a = np.where(valid, a, ninf)
    ends = np.array([2 * len(l) for l in labs])
    last = np.logaddexp(a[np.arange(len(names)), ends], a[np.arange(len(names)), ends - 1])
    return -last


def ctc_cost(lp: np.ndarray, names: list[str], scale: float = 2.0) -> np.ndarray:
    """Excess NLL per char over the best path, squashed to 0..1"""
    best = -lp.max(0).sum()
    x = (ctc_nll(lp, names) - best) / np.array([max(3, len(n)) for n in names])
    return 1 - np.exp(-np.maximum(x, 0) / scale)


def _clean(t: str) -> str:
    t = re.sub(r"^\[[^\]]*\]\s*", "", t.strip())
    return t.replace(" ", "")


def cost(text: str, name: str) -> float:
    t = _clean(text)
    d = Levenshtein.normalized_distance(t, name)
    dl = Levenshtein.normalized_distance(t.lower(), name.lower()) + 0.04
    return min(d, dl)


def match(rgb: np.ndarray, known: list[str], tab, prows, model: str, only: list[str] | None = None,
          max_cost: float = MAX_COST, margin: float = MARGIN) -> dict[str, str]:
    if tab is None or not known:
        return {}
    k = tab.k
    regions = regions_of(rgb, prows, k)
    if not regions:
        return {}
    crops = [norm_crop(rgb, r.prow.row.y, r.x0, r.x1, k) for r in regions]
    texts = read_crops(crops, model)
    C = np.array([[cost(t, n) for n in known] for t in texts])
    out = {}
    for i, j in assign(C, max_cost, margin):
        t = regions[i].prow.team
        if t and (only is None or known[j] in only):
            out[known[j]] = t
    return out


def read_teams(rgb: np.ndarray, known: list[str], model: str = MODEL) -> dict[str, str]:
    tab, prows = parse(rgb)
    return match(rgb, known, tab, prows, model)


# ---- leave-own-font-out model choice (bench only) ---------------------------


def loo_model(rgb: np.ndarray, tab, prows, known: list[str]) -> str:
    from g_bank import bank, excluded_for
    from g_match import setup_font, width_scores

    folds = [set(f) for f in json.loads((OUT / "folds.json").read_text())]
    ex = excluded_for(setup_font(rgb))
    if ex is None:  # unknown pack: the family of the best-width font
        fonts = [f for f in bank() if f.fid != "vanilla"]
        regions = regions_of(rgb, prows, tab.k) if tab else []
        if not regions or not known:
            return "loo0"
        best = fonts[int(np.argmin(width_scores(regions, known, fonts, tab.k)))]
        ex = {best.fid}
    if not ex:
        return "loo0"  # vanilla: in all folds
    hit = [i for i, f in enumerate(folds) if ex & f]
    assert len(hit) == 1, (ex, hit)
    return f"loo{hit[0]}"
