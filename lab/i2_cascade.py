"""I2 cascade: h5_cascade_ms, then word spotting (i2_spot) for names still
unknown. Lab shortcut: the h5_cascade_ms output is rebuilt from its bench
result (results/h5_cascade_ms.json; same train images, deterministic), keyed
by an image hash, so h5 does not run again. Set I2_LIVE=1 to run h5 live."""

import hashlib
import json
import os
import re
from functools import cache
from pathlib import Path

import numpy as np

import i2_spot
from data import image, label, train_names

CACHE = Path("/tmp/claude-1000/i2_hash.json")


@cache
def by_hash() -> dict[str, str]:
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    m = {hashlib.md5(image(n).tobytes()).hexdigest(): n for n in train_names()}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(m))
    return m


@cache
def h5_res() -> dict:
    p = Path(__file__).parent / "results" / "h5_cascade_ms.json"
    return json.loads(p.read_text())["images"]


def h5_out(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    if os.environ.get("I2_LIVE") == "1":
        import h5_cascade_ms

        return h5_cascade_ms.read_teams(rgb, known)
    n = by_hash()[hashlib.md5(rgb.tobytes()).hexdigest()]
    o = h5_res()[n]
    out = dict(o["correct"])
    for name, s in o["wrong"].items():
        out[name] = re.match(r"got (\w+)", s).group(1)
    out.update(o["npc"])
    out.update(o["extra"])
    assert set(o["correct"]) | set(o["wrong"]) | set(o["unknown"]) == {r["name"] for r in label(n)["rows"]}
    return out


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    out = h5_out(rgb, known)
    left = [n for n in known if n not in out]
    if left:
        # spot all names (the margin sees the found ones too), keep the left ones
        out.update({n: t for n, t in i2_spot.spot(rgb, known).items() if n in left})
    return out
