"""Self-learned font: shared parts of the d_* matchers.

extract(): rows (team + name glyphs) and calibration lines (header / footer
text, known strings in the same font). Font: per char a few glyph samples
(8 rows x w cols, font px, float). Glyph distance: soft IoU. Row x name cost:
DP over glyph runs vs chars (substitute, split, merge, skip).
"""

import hashlib
import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

import font
from common import parse
from rowparse import Word, words
from rows import Row, runs_of

H = 8  # glyph height in font px
W = 16  # padded glyph width in font px
CACHE = Path(__file__).parent / "results" / "dcache"

CALIB = [
    "You are playing on MC.HYPIXEL.NET",
    "Kills: # Final Kills: # Beds Broken: #",  # '#' = a number (skip)
    "Ranks, Boosters & MORE! STORE.HYPIXEL.NET",
]


@dataclass
class XRow:
    team: str | None
    glyphs: list[np.ndarray]  # name glyph runs, font px
    gaps: list[float]  # gap after each run (font px)
    bmp: np.ndarray  # whole name word, font px (H x w)


@dataclass
class Ext:
    k: int
    rows: list[XRow]
    calib: list[tuple[str, np.ndarray]] = field(default_factory=list)  # (char, glyph)


def to_font_px(m: np.ndarray, k: int) -> np.ndarray:
    w = max(1, round(m.shape[1] / k))
    return cv2.resize(m.astype(np.float32), (w, H), interpolation=cv2.INTER_AREA)


def split_word(w: Word, k: int) -> tuple[list[np.ndarray], list[float]]:
    spans = runs_of(w.mask.any(axis=0))
    gl = [to_font_px(w.mask[:, a:b], k) for a, b in spans]
    gaps = [(spans[i + 1][0] - spans[i][1]) / k for i in range(len(spans) - 1)] + [0.0]
    return gl, gaps


def _calib_lines(rgb: np.ndarray, tab, prows) -> list[list[Word]]:
    """Text lines above and below the rows (header / footer), plus the rows"""
    k = tab.k
    if not prows:
        return []
    ys = [p.row.y for p in prows]
    x0 = max(0, min(p.row.x0 for p in prows) - 90 * k)
    x1 = min(rgb.shape[1], max(p.row.x1 for p in prows) + 90 * k)
    out = [p.words for p in prows]
    for lo, hi in ((min(ys) - 30 * k, min(ys) - k), (max(ys) + 8 * k, max(ys) + 40 * k)):
        lo, hi = max(0, lo), min(rgb.shape[0] - 8 * k, hi)
        if hi <= lo:
            continue
        m = tab.mask[lo:hi, x0:x1].astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((1, 3 * k + 1), np.uint8))
        _, _, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        st = st[1:]
        st = st[(st[:, 3] >= 6 * k) & (st[:, 3] <= 8 * k + 1)]
        tops = sorted(set(int(t) for t in st[:, 1]))
        seen: list[int] = []
        for t in tops:
            if any(abs(t - s) <= k for s in seen) or lo + t in ys:
                continue
            seen.append(t)
            b = st[np.abs(st[:, 1] - t) <= k]
            r = Row(lo + t, x0 + int(b[:, 0].min()), x0 + int((b[:, 0] + b[:, 2]).max()), k)
            ws = words(rgb, tab.mask, r)
            if ws:
                out.append(ws)
    return out


def _calib_glyphs(lines: list[list[Word]], k: int) -> list[tuple[str, np.ndarray]]:
    out = []
    for ws in lines:
        counts = [len(runs_of(w.mask.any(axis=0))) for w in ws]
        for text in CALIB:
            exp = text.split(" ")
            # the line may have extra words (icons) left / right: try offsets
            for off in range(0, len(ws) - len(exp) + 1):
                sel = ws[off : off + len(exp)]
                ok = [e == "#" or counts[off + i] == len(e) for i, e in enumerate(exp)]
                if sum(ok) < 0.7 * len(exp) or not ok[-1]:
                    continue
                for e, w, good in zip(exp, sel, ok):
                    if e == "#" or not good:
                        continue
                    gl, _ = split_word(w, k)
                    out.extend(zip(e, gl))
                break
    return out


def _key(rgb: np.ndarray) -> str:
    return hashlib.blake2b(np.ascontiguousarray(rgb[::5, ::5]).tobytes(), digest_size=12).hexdigest()


def extract(rgb: np.ndarray) -> Ext | None:
    """Rows + calibration glyphs. Cached on disk when D_CACHE is set (dev only)"""
    path = CACHE / f"{_key(rgb)}.pkl" if os.environ.get("D_CACHE") else None
    if path and path.exists():
        return pickle.loads(path.read_bytes())
    tab, prows = parse(rgb)
    ext = None
    if tab is not None:
        k = tab.k
        rows = []
        seen = set()
        for p in prows:
            if p.name is None or (p.row.y, p.name.x0) in seen:
                continue  # (two-column finder can give a row twice)
            seen.add((p.row.y, p.name.x0))
            gl, gaps = split_word(p.name, k)
            rows.append(XRow(p.team, gl, gaps, to_font_px(p.name.mask, k)))
        ext = Ext(k, rows, _calib_glyphs(_calib_lines(rgb, tab, prows), k))
    if path:
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(ext))
    return ext


# ---- font model ----


def pad(g: np.ndarray) -> np.ndarray:
    out = np.zeros((H, W), np.float32)
    w = min(W, g.shape[1])
    out[:, :w] = g[:H, :w]
    return out


class Font:
    """Per char glyph samples; unknown chars from vanilla, width-warped"""

    def __init__(self, max_samples: int = 6) -> None:
        self.samples: dict[str, list[np.ndarray]] = {}
        self.max = max_samples
        self.vanilla = {c: g.astype(np.float32) for c, g in font.load().items() if c != " "}

    def add(self, c: str, g: np.ndarray) -> None:
        s = self.samples.setdefault(c, [])
        if len(s) < self.max:
            s.append(g)

    def width_ratio(self) -> float:
        r = [
            np.median([g.shape[1] for g in s]) / max(1, self.vanilla[c].shape[1])
            for c, s in self.samples.items()
            if c in self.vanilla and self.vanilla[c].shape[1] >= 3
        ]
        return float(np.median(r)) if len(r) >= 3 else 1.0

    def templates(self, chars: str) -> tuple[list[str], np.ndarray, np.ndarray]:
        """(char per template, padded templates T x H x W, widths)"""
        ratio = self.width_ratio()
        cs, ts, ws = [], [], []
        for c in sorted(set(chars)):
            s = self.samples.get(c)
            if not s:
                v = self.vanilla.get(c, self.vanilla["?"])
                w = max(1, round(v.shape[1] * ratio))
                s = [cv2.resize(v, (w, H), interpolation=cv2.INTER_LINEAR) if w != v.shape[1] else v]
            for g in s:
                cs.append(c)
                ts.append(pad(g))
                ws.append(g.shape[1])
        return cs, np.stack(ts), np.array(ws, np.float32)


def glyph_dist(G: np.ndarray, T: np.ndarray) -> np.ndarray:
    """1 - soft IoU, (n x H x W) vs (t x H x W) -> n x t; vertical shift +-1"""
    best = None
    for dy in (-1, 0, 1):
        Gs = np.roll(G, dy, axis=1)
        if dy == 1:
            Gs[:, 0] = 0
        elif dy == -1:
            Gs[:, -1] = 0
        a = Gs.reshape(len(G), 1, -1)
        b = T.reshape(1, len(T), -1)
        inter = np.minimum(a, b).sum(axis=2)
        union = np.maximum(a, b).sum(axis=2)
        d = 1 - inter / np.maximum(union, 1e-6)
        best = d if best is None else np.minimum(best, d)
    return best


def char_dist(glyphs: list[np.ndarray], font_: Font, chars: str) -> tuple[dict[str, int], np.ndarray]:
    """Distance of each glyph to each char (min over the char's samples)"""
    cs, T, _ = font_.templates(chars)
    G = np.stack([pad(g) for g in glyphs]) if glyphs else np.zeros((0, H, W), np.float32)
    D = glyph_dist(G, T)
    uniq = sorted(set(cs))
    idx = {c: i for i, c in enumerate(uniq)}
    out = np.full((len(glyphs), len(uniq)), 1.0, np.float32)
    for j, c in enumerate(cs):
        out[:, idx[c]] = np.minimum(out[:, idx[c]], D[:, j])
    return idx, out


def merged(glyphs: list[np.ndarray], gaps: list[float]) -> list[np.ndarray]:
    """Glyph i joined with glyph i+1 (a char split in two runs)"""
    out = []
    for i in range(len(glyphs) - 1):
        g = round(gaps[i])
        z = np.zeros((H, g), np.float32)
        out.append(np.concatenate([glyphs[i], z, glyphs[i + 1]], axis=1))
    return out


SKIP = 0.9
SPLIT = 0.15  # extra cost: one char in two runs
MERGE = 0.15  # extra cost: two chars in one run


def align_cost(
    name: str, idx: dict[str, int], D: np.ndarray, Dm: np.ndarray, Db: dict[tuple[int, str], float] | None
) -> tuple[float, list[tuple[int, int, int, int]]]:
    """DP: runs (D rows) vs chars of name. Returns (cost per char, path).
    Path steps (i0, i1, j0, j1): runs i0..i1 match chars j0..j1."""
    n, m = D.shape[0], len(name)
    inf = 1e9
    dp = np.full((n + 1, m + 1), inf)
    bk: dict[tuple[int, int], tuple[int, int]] = {}
    dp[0, 0] = 0
    ci = [idx[c] for c in name]
    for i in range(n + 1):
        for j in range(m + 1):
            v = dp[i, j]
            if v >= inf:
                continue
            if i < n and j < m:
                c = v + D[i, ci[j]]
                if c < dp[i + 1, j + 1]:
                    dp[i + 1, j + 1] = c
                    bk[(i + 1, j + 1)] = (i, j)
            if i + 1 < n and j < m:
                c = v + Dm[i, ci[j]] + SPLIT
                if c < dp[i + 2, j + 1]:
                    dp[i + 2, j + 1] = c
                    bk[(i + 2, j + 1)] = (i, j)
            if Db is not None and i < n and j + 1 < m:
                c = v + 2 * Db.get((i, name[j : j + 2]), 1.0) + MERGE
                if c < dp[i + 1, j + 2]:
                    dp[i + 1, j + 2] = c
                    bk[(i + 1, j + 2)] = (i, j)
            if i < n and v + SKIP < dp[i + 1, j]:
                dp[i + 1, j] = v + SKIP
                bk[(i + 1, j)] = (i, j)
            if j < m and v + SKIP < dp[i, j + 1]:
                dp[i, j + 1] = v + SKIP
                bk[(i, j + 1)] = (i, j)
    path = []
    cur = (n, m)
    while cur != (0, 0):
        prev = bk[cur]
        path.append((prev[0], cur[0], prev[1], cur[1]))
        cur = prev
    return float(dp[n, m]) / max(n, m), path[::-1]


def bigram_dists(
    glyphs: list[np.ndarray], font_: Font, names: list[str]
) -> dict[tuple[int, str], float]:
    """Distance of each run to each bigram of the names (two chars in one run)"""
    bigrams = sorted({nm[i : i + 2] for nm in names for i in range(len(nm) - 1)})
    if not glyphs or not bigrams:
        return {}
    cs, T, _ = font_.templates("".join(bigrams))
    first: dict[str, np.ndarray] = {}
    for c, t, in zip(cs, T):
        first.setdefault(c, t)
    bt = []
    for b in bigrams:
        g1 = first[b[0]]
        g2 = first[b[1]]
        w1 = int((g1.sum(axis=0) > 0).nonzero()[0].max() + 1) if g1.any() else 1
        w2 = int((g2.sum(axis=0) > 0).nonzero()[0].max() + 1) if g2.any() else 1
        bt.append(pad(np.concatenate([g1[:, :w1], np.zeros((H, 1), np.float32), g2[:, :w2]], axis=1)))
    wide = [g for g in glyphs]
    G = np.stack([pad(g) for g in wide])
    D = glyph_dist(G, np.stack(bt))
    # only runs wide enough to hold two chars
    out = {}
    for i, g in enumerate(glyphs):
        if g.shape[1] < 5:
            continue
        for j, b in enumerate(bigrams):
            out[(i, b)] = float(D[i, j])
    return out


def cost_matrix(
    ext: Ext, names: list[str], font_: Font, with_merge: bool = True
) -> tuple[np.ndarray, list[list[list[tuple[int, int, int, int]]]]]:
    chars = "".join(names)
    C = np.full((len(ext.rows), len(names)), 1.0)
    paths: list[list] = []
    for r, xr in enumerate(ext.rows):
        rp = []
        if not xr.glyphs:
            paths.append([[] for _ in names])
            continue
        idx, D = char_dist(xr.glyphs, font_, chars)
        mg = merged(xr.glyphs, xr.gaps)
        if mg:
            _, Dm = char_dist(mg, font_, chars)
        else:
            Dm = np.ones((0, D.shape[1]), np.float32)
        Db = bigram_dists(xr.glyphs, font_, names) if with_merge else None
        for j, nm in enumerate(names):
            # cheap prefilter: run count far from name length
            if abs(len(xr.glyphs) - len(nm)) > max(3, len(nm) // 2):
                rp.append([])
                continue
            C[r, j], p = align_cost(nm, idx, D, Dm, Db)
            rp.append(p)
        paths.append(rp)
    return C, paths


def learn_from(ext: Ext, font_: Font, pairs, names, paths, max_d: float = 0.45) -> int:
    """Add glyphs of matched rows (1 run = 1 char steps) as samples"""
    n = 0
    for r, j in pairs:
        xr = ext.rows[r]
        nm = names[j]
        for i0, i1, j0, j1 in paths[r][j]:
            if i1 - i0 == 1 and j1 - j0 == 1:
                font_.add(nm[j0], xr.glyphs[i0])
                n += 1
    return n
