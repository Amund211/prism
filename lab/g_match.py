"""Font-bank matcher: pick the best-fitting bank font(s) per image, render
the known names in it, IoU against the name regions, Hungarian + margin."""

import hashlib
import json
from pathlib import Path

import numpy as np

from common import assign, parse
from front_regions import NameRegion, name_region, regions_of  # noqa: F401  (re-export for lab callers)
from g_bank import BankFont, bank, excluded_for, ink_width, iou, render

WIDTH_TOL = 2.5  # GUI px: pairs further apart in ink width get no IoU


def width_scores(regions: list[NameRegion], known: list[str], fonts: list[BankFont], k: int) -> np.ndarray:
    """Per font (lower is better): minus the soft count of rows whose ink width
    fits some known name (junk rows count for no font)"""
    obs = np.array([(r.x1 - r.x0) / k for r in regions])
    out = []
    for f in fonts:
        pred = np.array([ink_width(f, n) for n in known])
        d = np.abs(obs[:, None] - pred[None, :]).min(axis=1)
        out.append(-np.exp(-((d / 0.7) ** 2)).sum())
    return np.array(out)


def cost_matrix(regions: list[NameRegion], known: list[str], f: BankFont, k: int) -> np.ndarray:
    obs = np.array([(r.x1 - r.x0) / k for r in regions])
    pred = np.array([ink_width(f, n) for n in known])
    near = np.abs(obs[:, None] - pred[None, :]) <= WIDTH_TOL
    cost = np.ones((len(regions), len(known)))
    tmpl: dict[int, np.ndarray] = {}
    for i, j in zip(*np.nonzero(near)):
        if j not in tmpl:
            tmpl[j] = render(f, known[j], k)
        cost[i, j] = 1 - iou(regions[i].mask, tmpl[j], shifts=1)
    return cost


def read(
    rgb: np.ndarray,
    known: list[str],
    top: int = 1,
    prune: int = 6,
    exclude: set[str] | None = None,
    max_cost: float = 0.4,  # g_tune.py sweep: margin barely matters
    margin: float = 0.12,
) -> dict[str, str]:
    tab, prows = parse(rgb)
    if tab is None or not known:
        return {}
    k = tab.k
    regions = regions_of(rgb, prows, k)
    if not regions:
        return {}
    fonts = [f for f in bank() if not exclude or f.fid not in exclude]
    ws = width_scores(regions, known, fonts, k)
    cand = [fonts[i] for i in np.argsort(ws)[:prune]]
    costs = [cost_matrix(regions, known, f, k) for f in cand]
    # font fit: total assignment cost (lower is better)
    fit = [np.sort(c.min(axis=1))[: max(3, len(regions) // 2)].mean() for c in costs]
    order = np.argsort(fit)[:top]
    cost = np.min([costs[i] for i in order], axis=0)
    out = {}
    for i, j in assign(cost, max_cost=max_cost, margin=margin):
        t = regions[i].prow.team
        if t:
            out[known[j]] = t
    return out


# ---- leave-own-font-out: find the image's setup.font (bench only) ----------

_MAP = Path(__file__).parent / "results/g_imgmap.json"


def image_key(rgb: np.ndarray) -> str:
    return hashlib.sha1(np.ascontiguousarray(rgb[::53, ::61]).tobytes()).hexdigest() + str(rgb.shape)


def setup_font(rgb: np.ndarray) -> str | None:
    if not _MAP.exists():
        from data import image, label, train_names

        m = {image_key(image(n)): label(n)["setup"]["font"] for n in train_names()}
        _MAP.parent.mkdir(exist_ok=True)
        _MAP.write_text(json.dumps(m))
    return json.loads(_MAP.read_text()).get(image_key(rgb))


def read_loo(rgb: np.ndarray, known: list[str], **kw) -> dict[str, str]:
    font = setup_font(rgb)
    ex = excluded_for(font)
    if ex is None:
        # unknown pack: drop the family of the best-fitting font
        tab, prows = parse(rgb)
        if tab is None:
            return {}
        k = tab.k
        regions = regions_of(rgb, prows, k)
        fonts = [f for f in bank() if f.fid != "vanilla"]
        if not regions or not known:
            return {}
        best = fonts[int(np.argmin(width_scores(regions, known, fonts, k)))]
        ex = {f.fid for f in fonts if f.family == best.family}
    return read(rgb, known, exclude=ex, **kw)
