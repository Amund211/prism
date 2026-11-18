"""u_exp.py [variant...] [--cache=SUFFIX]: decode variants on
results/tl/ucache*.pkl, scored with the X2 policy (tl_sweep) and a tau sweep.

Variants replace the name-crop read before the policy runs:
  greedy  as tl_cache (baseline)
  beam    CTC prefix beam top-1 (name crop)
  avgy    greedy on the mean prob of the name crop and the dy +-1 crops
  tta     N-best from name + shifted crops, pick min summed NLL over all crops
  ttab    tta, also with the row crop's name as a candidate
Each also with conf = sequence posterior (suffix _post) in place of min char prob."""

import json
import multiprocessing
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import tl_sweep
from data import label
from tbench import score, summarize
from tl_cache import decode_conf
from tl_sweep import name_of
from u_decode import beam, posterior, rescore

SUF = next((a[8:] for a in sys.argv if a.startswith("--cache=")), "")
CACHE = Path(__file__).parent / f"results/tl/ucache{SUF}.pkl"
X2 = tl_sweep.POLICIES["X2 W2 + letter check: drop team"]


def nb(lp):
    return beam(lp.astype(np.float32), 8)


def region_variants(r: dict) -> dict:
    """variant -> (text, per-char conf) for the name crop"""
    out = {"greedy": r["name"]}
    ln = r["lp_name"].astype(np.float32)
    b = nb(ln)
    post = posterior(b)
    out["beam"] = (b[0][0], [1.0] * len(b[0][0]))
    out["beam_post"] = (b[0][0], [post] * len(b[0][0]))
    out["greedy_post"] = (r["name"][0], [post] * len(r["name"][0]))
    ys = [ln] + [x.astype(np.float32) for x in r["lp_tta"][3:5] if x.shape == ln.shape]
    m = np.log(np.mean([np.exp(x) for x in ys], 0) + 1e-12)
    out["avgy"] = decode_conf(m)
    allc = [ln] + [x.astype(np.float32) for x in r["lp_tta"]]
    cands = {t for t, _ in b[:4]}
    for x in allc[1:]:
        cands |= {t for t, _ in nb(x)[:2]}
    cands = sorted(cands)
    s = rescore(cands, allc)
    best = cands[int(np.argmin(s))]
    ss = np.sort(s)
    # posterior over candidates from the summed NLL, per crop
    p = 1.0 / np.exp(-(ss - ss[0]) / len(allc)).sum()
    out["tta"] = (best, [1.0] * len(best))
    out["tta_post"] = (best, [float(p)] * len(best))
    return out


def one(item):
    name, img = item
    regs = []
    for r in img["regions"]:
        v = region_variants(r)
        regs.append({k: v2 for k, v2 in r.items() if not k.startswith("lp_")} | {"v": v})
    return name, {k: v for k, v in img.items() if k != "regions"} | {"regions": regs}


def run(cache, var, tau):
    res = {}
    for n, img in cache.items():
        im = dict(img)
        im["regions"] = [dict(r, name=r["v"][var]) for r in img["regions"]]
        res[n] = (score(label(n), tl_sweep.policy(im, **(X2 | {"tau": tau}))), 0.0)
    return summarize(res)


def main():
    raw = pickle.loads(CACHE.read_bytes())
    out = CACHE.with_name(f"uvar{SUF}.pkl")
    if out.exists():
        cache = pickle.loads(out.read_bytes())
    else:
        with ProcessPoolExecutor(3, mp_context=multiprocessing.get_context("fork")) as ex:
            cache = dict(ex.map(one, raw.items()))
        out.write_bytes(pickle.dumps(cache))
    sel = [a for a in sys.argv[1:] if not a.startswith("--")] or [
        "greedy", "beam", "avgy", "tta", "greedy_post", "beam_post", "tta_post"]
    keys = ["full", "w_full", "bad_reads", "precision", "w_precision", "snap_correct", "snap_wrong"]
    for var in sel:
        for tau in (0.0, 0.5, 0.7, 0.9, 0.97):
            s = run(cache, var, tau)
            print(f"{var:12s} tau{tau:5.2f}", json.dumps({k: s[k] for k in keys}), flush=True)


if __name__ == "__main__":
    main()
