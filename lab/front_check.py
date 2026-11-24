"""Check the front step (tl_front.front -> regions_of -> norm_crop) on the train split.

  front_check.py dump LAB OUT.json   hash the full front output per train image, with LAB first on sys.path
  front_check.py diff A.json B.json  compare two dumps (exit 1 on any difference)
  front_check.py purity LAB          the front imports only front modules, and names no fonts / env vars

Run each dump in its own process: the old and new lab use the same module names."""

import dataclasses
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

FRONT = ["tl_front", "j3_grid", "front_regions", "grid3", "ping_grid", "lunar_mask", "bgmask", "textmask",
         "rows", "common", "rowparse", "guiscale"]
FORBIDDEN = re.compile(r"resource_packs|\bbank\(|os\.environ|getenv")
# only LAB may give lab modules, not this script's own dir
sys.path[:] = [p for p in sys.path if p and Path(p).resolve() != Path(__file__).resolve().parent]


def feed(h, o) -> None:
    """Hash any front value: dataclasses by field, arrays with dtype and shape"""
    if dataclasses.is_dataclass(o):
        h.update(type(o).__name__.encode())
        for f in dataclasses.fields(o):
            h.update(f.name.encode())
            feed(h, getattr(o, f.name))
    elif isinstance(o, np.ndarray):
        h.update(f"nd{o.dtype}{o.shape}".encode())
        h.update(np.ascontiguousarray(o).tobytes())
    elif isinstance(o, (list, tuple)):
        h.update(f"{type(o).__name__}{len(o)}".encode())
        for x in o:
            feed(h, x)
    elif o is None or isinstance(o, (bool, int, float, str, np.generic)):
        h.update(f"{type(o).__name__}:{o!r};".encode())
    else:
        raise TypeError(type(o))


def dump(lab: str, out: str) -> None:
    sys.path.insert(0, lab)
    import data

    assert data.SPLIT == "train", "train split only"
    from tl_front import front

    try:
        from front_regions import norm_crop, regions_of
    except ImportError:  # old lab
        from g_match import regions_of
        from i4_synth import norm_crop

    res = {}
    for name in data.train_names():
        rgb = data.image(name)
        finder, tab, prows = front(rgb)
        h = hashlib.sha256()
        feed(h, (finder, tab, prows))
        n = 0
        if tab is not None:
            k = tab.k
            regions = regions_of(rgb, prows, k)
            n = len(regions)
            feed(h, regions)
            for r in regions:
                feed(h, norm_crop(rgb, r.prow.row.y, r.x0, r.x1, k))
                feed(h, norm_crop(rgb, r.prow.row.y, r.prow.row.x0, r.prow.row.x1, k))
        res[name] = {"finder": finder, "regions": n, "sha256": h.hexdigest()}
    Path(out).write_text(json.dumps(res, indent=1, sort_keys=True))
    print(len(res), "images,", sum(r["regions"] for r in res.values()), "regions ->", out)


def diff(a: str, b: str) -> int:
    x, y = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
    bad = sorted(n for n in x.keys() | y.keys() if x.get(n) != y.get(n))
    for n in bad:
        print("DIFF", n, x.get(n), y.get(n))
    print(f"{len(x)} vs {len(y)} images, {len(bad)} differ")
    return 1 if bad or not x else 0


def purity(lab: str) -> int:
    root = Path(lab).resolve()
    sys.path.insert(0, str(root))
    for m in ("tl_front", "front_regions"):
        __import__(m)
    loaded = {n for n, m in sys.modules.items() if Path(getattr(m, "__file__", None) or "/").parent == root}
    errs = [f"imports lab module {n}" for n in sorted(loaded - set(FRONT) - {"__main__"})]
    errs += [f"imports {n}" for n in ("PIL", "torch", "onnxruntime") if n in sys.modules]
    for n in FRONT:
        for i, line in enumerate((root / f"{n}.py").read_text().splitlines(), 1):
            if FORBIDDEN.search(line) or line.startswith("if __name__"):
                errs.append(f"{n}.py:{i}: {line.strip()}")
    for e in errs:
        print("FAIL", e)
    print("purity:", "ok" if not errs else f"{len(errs)} problems", sorted(loaded))
    return 1 if errs else 0


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    sys.exit({"dump": dump, "diff": diff, "purity": purity}[cmd](*args) or 0)
