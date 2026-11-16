"""I1: h5 colour-layer OCR, but the team letter check uses the SHAPE of the
first glyph of the layer segment (font bank templates, plain + bold, fonts
calibrated per image), not OCR.

MODE (module global):
  "none"  no letter check
  "ocr"   h5 rule (OCR letter must match the layer)
  "shape" shape letter must match the layer
  "or"    shape OR OCR letter matches the layer
  "or_c"  "or", and the letter colour must equal the name colour
"""

from functools import cache

import numpy as np
from rapidfuzz import fuzz

import e2c_rowband as rb
import g_bank
import h5_layer as h5
from common import assign
from rowparse import LETTER
from textmask import Shadow

MODE = "or"
C = 12  # canvas
MIN_IOU, MIN_MARGIN = 0.6, 0.05
MIN_GAP = 2  # empty columns after the letter (a space)
COL_TOL = 30
CALIB = 5  # fonts kept per image (0: all)
BY_LETTER = {v: k for k, v in LETTER.items()}


@cache
def templates() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(N, C*C) templates on the canvas at (1, 1), letters (N,), font (N,)"""
    seen, arrs, labs, fonts = set(), [], [], []
    for fi, f in enumerate(g_bank.bank()):
        for L in LETTER.values():
            g = g_bank.render(f, L, 1)
            if g.size == 0:
                continue
            b = np.zeros((g.shape[0], g.shape[1] + 1), bool)
            b[:, :-1] |= g
            b[:, 1:] |= g
            for t in (g, b):
                t = crop(t)
                if t is None or max(t.shape) > C - 2:
                    continue
                key = (fi, L, t.shape, t.tobytes())
                if key in seen:
                    continue
                seen.add(key)
                cv = np.zeros((C, C), np.float32)
                cv[1 : 1 + t.shape[0], 1 : 1 + t.shape[1]] = t
                arrs.append(cv.ravel())
                labs.append(L)
                fonts.append(fi)
    return np.array(arrs), np.array(labs), np.array(fonts)


def crop(m: np.ndarray) -> np.ndarray | None:
    ys, xs = np.nonzero(m)
    if not len(ys):
        return None
    return m[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


def ious(g: np.ndarray) -> np.ndarray | None:
    """IoU of the glyph with every template (best of 9 shifts)"""
    g = crop(g)
    if g is None or max(g.shape) > C - 2 or g.shape[0] < 5:
        return None
    T = templates()[0]
    shifts = []
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            cv = np.zeros((C, C), np.float32)
            cv[dy : dy + g.shape[0], dx : dx + g.shape[1]] = g
            shifts.append(cv.ravel())
    S = np.array(shifts)
    inter = S @ T.T
    union = S.sum(1)[:, None] + T.sum(1)[None, :] - inter
    return (inter / np.maximum(union, 1)).max(0)


def calibrate(all_ious: list[np.ndarray]) -> np.ndarray:
    """template mask of the CALIB fonts that best explain this image's letters"""
    fonts = templates()[2]
    if not CALIB or not all_ious:
        return np.ones(len(fonts), bool)
    nf = fonts.max() + 1
    tot = np.zeros(nf)
    for v in all_ious:
        per = np.zeros(nf)
        np.maximum.at(per, fonts, v)
        tot += per
    return np.isin(fonts, np.argsort(-tot)[:CALIB])


def decide(v: np.ndarray | None, use: np.ndarray) -> tuple[str | None, float, float]:
    """(letter, iou, margin over the best other letter)"""
    if v is None:
        return None, 0.0, 0.0
    labs = templates()[1]
    best = {L: float(v[use & (labs == L)].max(initial=0)) for L in LETTER.values()}
    order = sorted(best, key=best.get, reverse=True)
    return order[0], best[order[0]], best[order[0]] - best[order[1]]


def shape_team(sh: tuple[str | None, float, float]) -> str | None:
    L, iou, mg = sh
    return BY_LETTER[L] if L and iou >= MIN_IOU and mg >= MIN_MARGIN else None


def first_glyph(seg: np.ndarray) -> tuple[np.ndarray, int, int] | None:
    """(mask, x0, x1) of the first column run, if a space follows it"""
    on = seg[1:9].any(0)
    xs = np.nonzero(on)[0]
    if not len(xs):
        return None
    a = b = xs[0]
    while b < len(on) and on[b]:
        b += 1
    gap = 0
    while b + gap < len(on) and not on[b + gap]:
        gap += 1
    if gap < MIN_GAP or b + gap >= len(on):
        return None
    return seg[:, a:b], a, b


REFINE_TOL = 40


def refine(fg: tuple[np.ndarray, int, int], px: np.ndarray) -> np.ndarray:
    """The shadow test drops bold-letter px whose shadow falls on text: take
    the letter columns again by its median colour (rows 1..8)"""
    g, a, b = fg
    if not REFINE_TOL:
        return g[1:9]
    c = np.median(px[:, a:b][g].astype(int), axis=0)
    same = np.abs(px[1:9, a:b].astype(int) - c).max(axis=2) <= REFINE_TOL
    return same | g[1:9]


def colour_ok(seg: np.ndarray, px: np.ndarray, a: int, b: int, g: np.ndarray) -> bool:
    lm = np.zeros(seg.shape, bool)
    lm[:, a:b] = g
    rest = seg & ~lm
    if not rest.any():
        return False
    cl = np.median(px[lm].astype(int), axis=0)
    cr = np.median(px[rest].astype(int), axis=0)
    return bool(np.abs(cl - cr).max() <= COL_TOL)


Shape = tuple[str | None, float, float]
Line = tuple[tuple[str, ...], str, Shape, bool]


def segs(rgb: np.ndarray, min_px: int = 12) -> list[tuple[np.ndarray, str, np.ndarray]]:
    """(segment mask, layer team, segment pixels): h5_layer.layer_lines without OCR"""
    bs = rb.bands(rgb)
    if not bs:
        return []
    k = bs[0][3]
    sh = Shadow(rgb).mask(k)
    h, w, _ = rgb.shape
    out = []
    seen: set = set()
    for y, x0, x1, k in bs:
        y0, y1 = max(0, y - k), min(h - k, y + 9 * k)
        x0 = max(0, x0 - h5.WIDEN * k)
        x1 = min(w - k, x1 + h5.WIDEN // 4 * k)
        sub = sh[y0:y1:k, x0:x1:k]
        ys, xs = np.nonzero(sub)
        if len(ys) < min_px:
            continue
        iy, ix = y0 + ys * k, x0 + xs * k
        t = h5.hue(rgb[iy, ix])
        s = h5.hue(rgb[iy + k, ix + k], 4)
        t = np.where(t >= 0, t, s)
        px = rgb[y0:y1:k, x0:x1:k]
        for ti in np.unique(t):
            if ti < 0 or (t == ti).sum() < min_px:
                continue
            m = np.zeros(sub.shape, bool)
            m[ys[t == ti], xs[t == ti]] = True
            m = h5.fill(px, m)
            for a, b in h5.segments(m):
                seg = m[:, a:b]
                key = (h5.TEAMS[ti], y, seg.tobytes(), seg.shape)
                if seg.sum() < min_px or key in seen:
                    continue
                seen.add(key)
                out.append((seg, h5.TEAMS[ti], px[:, a:b]))
    return out


def shapes(ss: list[tuple[np.ndarray, str, np.ndarray]]) -> list[tuple[Shape, bool]]:
    fgs = [first_glyph(seg) for seg, _, _ in ss]
    vs = [ious(refine(fg, px)) if fg else None for fg, (_, _, px) in zip(fgs, ss)]
    use = calibrate([v for v in vs if v is not None])
    out = []
    for (seg, _, px), fg, v in zip(ss, fgs, vs):
        col = colour_ok(seg, px, fg[1], fg[2], fg[0]) if fg else False
        out.append((decide(v, use), col))
    return out


def layer_lines(rgb: np.ndarray, known: list[str] | None = None) -> list[Line]:
    ss = segs(rgb)
    out: list[Line] = []
    for (seg, team, _), (sh, col) in zip(ss, shapes(ss)):
        txts: list[str] = []
        for sc in h5.SCALES:
            txt = h5.rec(h5.render(seg, sc))
            if txt.strip():
                txts.append(txt)
            if not known or best(txts, known, team, sh, col) >= h5.GOOD:
                break
        if txts:
            out.append((tuple(txts), team, sh, col))
    return out


def score(name: str, line: str, team: str, sh: Shape, col: bool,
          mode: str | None = None) -> float:
    mode = mode or MODE
    line = line.replace(" ", "")
    low = line.lower()
    if any(w_ in low for w_ in rb.NOT_ROWS):
        return 0.0
    al = fuzz.partial_ratio_alignment(name.lower(), low)
    if al is None:
        return 0.0
    s = al.score / 100 * min(1.0, (al.dest_end - al.dest_start) / max(1, len(name)))
    pre = "".join(c for c in line[: al.dest_start] if c.isalnum())
    if len(pre) > 3:
        return 0.0
    ocr_ok = False
    if pre:
        c = h5.LOOK.get(pre[-1], pre[-1])
        ocr_ok = rb.BY_LETTER.get(h5.LOOK.get(c, c).upper()) == team
    shape_ok = shape_team(sh) == team
    if mode == "none":
        ok = True
    elif mode == "ocr":
        ok = ocr_ok
    elif mode == "shape":
        ok = shape_ok
    else:
        ok = shape_ok or ocr_ok
        if mode == "or_c":
            ok = ok and col
    return s if ok else 0.0


def best(txts, known, team, sh, col) -> float:
    return max((score(n, t, team, sh, col) for t in txts for n in known), default=0.0)


def match(lines: list[Line], known: list[str],
          max_cost: float = h5.MAX_COST, margin: float = h5.MARGIN) -> dict[str, str]:
    lines = list(dict.fromkeys(lines))
    if not lines or not known:
        return {}
    cost = np.array([[1 - best(ts, [n], tm, sh, col) for n in known]
                     for ts, tm, sh, col in lines])
    return {known[j]: lines[i][1] for i, j in assign(cost, max_cost, margin)}


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return match(layer_lines(rgb, known), known)
