"""C1: glyph-run alignment. Runs of the name word (width, top, bottom) vs the
glyphs of each name. Glyph model per image: vanilla x scale, then refined
per char from confident matches (EM). All-caps fonts: a second model."""

import numpy as np

from c_feats import Glyph, RowF, assign_loo, char_glyph, feats

SKIP = 0.9  # a run or char with no partner
MERGE = 0.25  # per extra char in one run (touching glyphs)
SPLIT = 0.35  # one char as two runs
H_W = 0.5  # weight of the height terms


def qmap(src: list[float], dst: list[float]):
    """Monotone map: each distinct src value -> dst value at the same quantile
    (mid of its cumulative range). Font calibration by histogram matching."""
    s = np.sort(np.asarray(src, float))
    d = np.sort(np.asarray(dst, float))
    vals = np.unique(s)
    lo = np.searchsorted(s, vals, "left") / len(s)
    hi = np.searchsorted(s, vals, "right") / len(s)
    tgt = np.quantile(d, (lo + hi) / 2)
    tgt = np.maximum.accumulate(tgt)
    table = dict(zip(vals.tolist(), tgt.tolist()))
    return lambda v: table.get(v, float(np.interp(v, vals, tgt)))


class Model:
    """char -> expected run glyph (image font px)"""

    def __init__(self, s: float, caps: bool = False, learned: dict[str, Glyph] | None = None, maps=None):
        self.s = s
        self.caps = caps
        self.learned = learned or {}
        self.maps = maps  # (width, top, bot) quantile maps, or None: scale only
        self._cache: dict[str, Glyph] = {}

    def glyph(self, c: str) -> Glyph:
        g = self._cache.get(c)
        if g is None:
            if c in self.learned:
                g = self.learned[c]
            else:
                v = char_glyph(c.upper() if self.caps else c)
                if self.maps:
                    fw, ft, fb = self.maps
                    g = Glyph(fw(v.w), ft(v.top), fb(v.bot), v.ink)
                else:
                    g = Glyph(v.w * self.s, v.top, v.bot, v.ink)
            self._cache[c] = g
        return g

    def name(self, n: str) -> list[Glyph]:
        return [self.glyph(c) for c in n]


def calibrated(rows: list[RowF], known: list[str], caps: bool = False) -> Model:
    runs = [g for r in rows if r.team for g in r.runs] or [g for r in rows for g in r.runs]
    chars = [char_glyph(c.upper() if caps else c) for n in known for c in n]
    if len(runs) < 10 or not chars:
        return Model(glyph_scale(rows, known, caps), caps)
    maps = tuple(qmap([getattr(c, a) for c in chars], [getattr(g, a) for g in runs]) for a in ("w", "top", "bot"))
    return Model(glyph_scale(rows, known, caps), caps, maps=maps)


def gcost(r: Glyph, w: float, top: float, bot: float) -> float:
    dw = min(1.5, abs(r.w - w) / max(w, 1.5))
    dh = min(1.0, abs(r.top - top) / 2) + min(1.0, abs(r.bot - bot) / 1.5)
    return dw + H_W * dh


def align(runs: list[Glyph], chars: list[Glyph], s: float, path: bool = False):
    """DP alignment cost / max(n, m); with path: also [(run i, (j0, j1))] of 1:t matches"""
    n, m = len(runs), len(chars)
    D = np.full((n + 1, m + 1), 1e9)
    B = {}
    D[0, :] = np.arange(m + 1) * SKIP
    D[:, 0] = np.arange(n + 1) * SKIP
    for i in range(1, n + 1):
        r = runs[i - 1]
        for j in range(1, m + 1):
            best, arg = D[i - 1, j] + SKIP, ("skip_run",)
            v = D[i, j - 1] + SKIP
            if v < best:
                best, arg = v, ("skip_char",)
            top, bot, w = 9.0, -1.0, -s
            for t in range(1, 4):
                if j - t < 0:
                    break
                c = chars[j - t]
                w += c.w + s  # merged chars: + 1 px gap each
                top, bot = min(top, c.top), max(bot, c.bot)
                v = D[i - 1, j - t] + gcost(r, w, top, bot) + MERGE * (t - 1)
                if v < best:
                    best, arg = v, ("match", t)
            if i >= 2:
                r2 = runs[i - 2]
                both = Glyph(r.w + r2.w + s, min(r.top, r2.top), max(r.bot, r2.bot), 0)
                c = chars[j - 1]
                v = D[i - 2, j - 1] + gcost(both, c.w, c.top, c.bot) + SPLIT
                if v < best:
                    best, arg = v, ("split",)
            D[i, j] = best
            B[i, j] = arg
    cost = D[n, m] / max(m, n, 1)
    if not path:
        return cost
    out = []
    i, j = n, m
    while i > 0 and j > 0:
        a = B[i, j]
        if a[0] == "skip_run":
            i -= 1
        elif a[0] == "skip_char":
            j -= 1
        elif a[0] == "split":
            i, j = i - 2, j - 1
        else:
            out.append((i - 1, j - a[1], j))
            i, j = i - 1, j - a[1]
    return cost, out


def cost_matrix(rows: list[RowF], known: list[str], model: Model) -> np.ndarray:
    names = [model.name(n) for n in known]
    return np.array([[align(r.runs, g, model.s) for g in names] for r in rows])


def glyph_scale(rows: list[RowF], known: list[str], caps: bool = False) -> float:
    rw = [g.w for r in rows for g in r.runs]
    cw = [char_glyph(c.upper() if caps else c).w for n in known for c in n]
    if not rw or not cw:
        return 1.0
    return float(np.median(rw) / max(np.median(cw), 1))


def learn(rows: list[RowF], known: list[str], model: Model, pairs: list[tuple[int, int]]) -> Model:
    """Per-char glyph from 1:1 run matches of confident pairs (median)"""
    obs: dict[str, list[Glyph]] = {}
    num = den = 0.0
    for i, j in pairs:
        name = known[j]
        _, path = align(rows[i].runs, model.name(name), model.s, path=True)
        for ri, j0, j1 in path:
            if j1 - j0 == 1:
                obs.setdefault(name[j0], []).append(rows[i].runs[ri])
                num += rows[i].runs[ri].w
                den += char_glyph(name[j0].upper() if model.caps else name[j0]).w
    s = num / den if den > 0 else model.s
    learned = {
        c: Glyph(
            float(np.median([g.w for g in gs])),
            float(np.median([g.top for g in gs])),
            float(np.median([g.bot for g in gs])),
            0,
        )
        for c, gs in obs.items()
        if len(gs) >= 2
    }
    return Model(s, model.caps, learned)


ACCEPT = (0.40, 0.07)
EM_ACCEPT = (0.30, 0.10)  # stricter: the pairs we learn the font from


def costs(rows: list[RowF], known: list[str], rounds: int = 0, modes: tuple[bool, ...] = (False,)) -> np.ndarray:
    """rounds > 0: EM font learning; modes (False, True): also try all-caps.
    Neither helped on train (more wrongs), so off by default."""
    best = None
    for caps in modes:
        model = Model(glyph_scale(rows, known, caps), caps)
        cost = cost_matrix(rows, known, model)
        for _ in range(rounds):
            pairs = assign_loo(cost, *EM_ACCEPT)
            if len(pairs) < 3:
                break
            model = learn(rows, known, model, pairs)
            cost = cost_matrix(rows, known, model)
        score = np.sort(cost.min(axis=1))[: max(1, min(len(rows), len(known)) * 2 // 3)].mean()
        if best is None or score < best[0]:
            best = (score, cost)
    return best[1]


def match(rows: list[RowF], known: list[str], max_cost: float = ACCEPT[0], margin: float = ACCEPT[1]) -> dict[str, str]:
    if not rows or not known:
        return {}
    pairs = assign_loo(costs(rows, known), max_cost, margin)
    return {known[j]: rows[i].team for i, j in pairs if rows[i].team}


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return match(feats(rgb), known)
