"""H5 layer: colour-layer OCR. Per tab row band and per palette colour, keep
only the shadowed text pixels of that colour (by text hue, else by shadow hue
for remapped packs), render black on white at font scale, OCR (rec only).
The team is the layer, so no letter or colour reading is needed."""

import cv2
import numpy as np
from rapidfuzz import fuzz

import e2c_rowband as rb
from common import assign
from e2_rapidocr import engine
from textmask import Shadow

# hue code: bit 4 R high, 2 G high, 1 B high
CODE = {4: "red", 1: "blue", 2: "green", 6: "yellow", 3: "aqua", 5: "pink"}
MAX_COST, MARGIN = 0.35, 0.1
SCALE = 5
WIDEN = 220  # font px


def hue(px: np.ndarray, mul: int = 1) -> np.ndarray:
    """team index per pixel (into TEAMS), -1 if unclear"""
    px = px.astype(np.int32) * mul
    m = px.max(axis=1)
    hi = px * 4 >= m[:, None] * 3
    lo = px * 2 <= m[:, None]
    ok = (hi | lo).all(axis=1) & (m > 0)
    code = hi[:, 0] * 4 + hi[:, 1] * 2 + hi[:, 2]
    out = np.full(len(px), -1)
    for c, t in CODE.items():
        out[ok & (code == c)] = TEAMS.index(t)
    g = ok & (code == 7)
    out[g & (m >= 190)] = TEAMS.index("white")
    out[g & (m >= 60) & (m <= 115)] = TEAMS.index("gray")
    return out


TEAMS = ["red", "blue", "green", "yellow", "aqua", "pink", "white", "gray"]


def render(m: np.ndarray, scale: int = SCALE, pad: int = 8) -> np.ndarray:
    m = m.repeat(scale, axis=0).repeat(scale, axis=1)
    out = np.full((m.shape[0] + 2 * pad, m.shape[1] + 2 * pad), 255, np.uint8)
    out[pad : pad + m.shape[0], pad : pad + m.shape[1]][m] = 0
    return np.repeat(out[:, :, None], 3, axis=2)


def rec(img: np.ndarray) -> str:
    r = engine()(img, use_det=False, use_cls=False, use_rec=True)
    return "".join(r.txts or ())


def fill(px: np.ndarray, m: np.ndarray, tol: int = 24) -> np.ndarray:
    """The shadow test misses text pixels whose shadow spot is text too:
    add pixels near the layer that have its median colour."""
    c = np.median(px[m].astype(int), axis=0)
    near = cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    same = (np.abs(px.astype(int) - c).max(axis=2) <= tol) & near
    return m | same


def layer_lines(rgb: np.ndarray, known: list[str] | None = None,
                min_px: int = 12) -> list[tuple[tuple[str, ...], str]]:
    """(texts, team) per band segment and colour layer; more OCR passes
    (SCALES) while no known name reads well"""
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
        # the row finder can miss the name column (some packs): look wider
        x0 = max(0, x0 - WIDEN * k)
        x1 = min(w - k, x1 + WIDEN // 4 * k)
        sub = sh[y0:y1:k, x0:x1:k]
        ys, xs = np.nonzero(sub)
        if len(ys) < min_px:
            continue
        iy, ix = y0 + ys * k, x0 + xs * k
        t = hue(rgb[iy, ix])
        s = hue(rgb[iy + k, ix + k], 4)
        t = np.where(t >= 0, t, s)
        for ti in np.unique(t):
            if ti < 0 or (t == ti).sum() < min_px:
                continue
            m = np.zeros(sub.shape, bool)
            m[ys[t == ti], xs[t == ti]] = True
            m = fill(rgb[y0:y1:k, x0:x1:k], m)
            for a, b in segments(m):
                seg = m[:, a:b]
                key = (TEAMS[ti], y, seg.tobytes(), seg.shape)
                if seg.sum() < min_px or key in seen:
                    continue
                seen.add(key)
                txts: list[str] = []
                for sc in SCALES:
                    txt = rec(render(seg, sc))
                    if txt.strip():
                        txts.append(txt)
                    if not known or best(txts, known, TEAMS[ti]) >= GOOD:
                        break
                if txts:
                    out.append((tuple(txts), TEAMS[ti]))
    return out


SCALES = (5,)
GOOD = 0.9


def best(txts: list[str], known: list[str], team: str) -> float:
    return max((score(n, t, team) for t in txts for n in known), default=0.0)


def segments(m: np.ndarray, gap: int = 10) -> list[tuple[int, int]]:
    """column runs of the mask split at >= gap empty columns"""
    xs = np.nonzero(m.any(axis=0))[0]
    if not len(xs):
        return []
    cut = np.nonzero(np.diff(xs) > gap)[0]
    starts = [xs[0]] + [xs[i + 1] for i in cut]
    ends = [xs[i] + 1 for i in cut] + [xs[-1] + 1]
    return [(max(0, a - 1), b + 1) for a, b in zip(starts, ends)]


LOOK = {**rb.LOOKALIKE, "H": "W", "r": "Y"}
NEED_PRE = True
STRICT = True  # the glyph before the name must read as this layer's letter


def score(name: str, line: str, team: str) -> float:
    """similarity of the name in the line; 0 if the glyphs before the name
    do not look like the team letter of this layer"""
    line = line.replace(" ", "")
    low = line.lower()
    if any(w in low for w in rb.NOT_ROWS):
        return 0.0
    al = fuzz.partial_ratio_alignment(name.lower(), low)
    if al is None:
        return 0.0
    s = al.score / 100 * min(1.0, (al.dest_end - al.dest_start) / max(1, len(name)))
    pre = "".join(c for c in line[: al.dest_start] if c.isalnum())
    if len(pre) > 3 or (NEED_PRE and not pre):
        return 0.0  # no letter: spectator / respawning, or not a row start
    if pre:
        c = LOOK.get(pre[-1], pre[-1])
        lt = rb.BY_LETTER.get(LOOK.get(c, c).upper())
        if lt != team and (STRICT or lt is not None):
            return 0.0
    return s


def match(lines: list[tuple[str, str]], known: list[str],
          max_cost: float = MAX_COST, margin: float = MARGIN) -> dict[str, str]:
    lines = list(dict.fromkeys(lines))
    if not lines or not known:
        return {}
    cost = np.array([[1 - best(list(ts), [n], tm) for n in known] for ts, tm in lines])
    return {known[j]: lines[i][1] for i, j in assign(cost, max_cost, margin)}


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return match(layer_lines(rgb, known), known)
