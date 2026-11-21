"""u_files.py DIR: front end + mix_wide reads on <name>.png + <name>.json in DIR
(not in the manifest yet). Prints finder, k, rows found, union / open score."""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

import json  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import u_cache  # noqa: E402
from tbench import score  # noqa: E402
from u_decode import beam, posterior  # noqa: E402
from u_union import read  # noqa: E402

d = Path(sys.argv[1])
for p in sorted(d.glob("*.png")):
    lab = json.loads(p.with_suffix(".json").read_text())
    with Image.open(p) as im:
        rgb = np.asarray(im.convert("RGB"))
    u_cache.image = lambda _n, rgb=rgb: rgb  # one() loads by name
    t = time.perf_counter()
    _, img = u_cache.one(p.stem)
    ms = 1000 * (time.perf_counter() - t)
    for r in img["regions"]:
        b = beam(r["lp_name"].astype(np.float32), 8)
        r["v"] = {"greedy_post": (r["name"][0], [posterior(b)] * len(r["name"][0]))}
    ks = sorted({r["k"] for r in img["regions"]})
    u = score(lab, read(img, list(lab["known"]), "union", "g3", 0.7))
    o = score(lab, read(img, list(lab["known"]), "open", "g3", 0.0))
    print(f"{p.stem[:58]:58s} {rgb.shape[1]}x{rgb.shape[0]} gs {lab['setup']['gui_scale']} "
          f"finder {img['finder']:4s} k {ks} regions {len(img['regions']):2d} rows {len(lab['rows'])} "
          f"union {len(u['full'])} open {len(o['full'])} bad {o['n_reads'] - o['n_good']} {ms:.0f} ms", flush=True)
