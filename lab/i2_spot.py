"""I2: row-free word spotting. Render each known name (vanilla + bank fonts)
at font px, NCC-match it on the shadow text mask (downsampled to font px),
read the team colour at the hit, require a same-colour letter on the left,
Hungarian + margin over (hit, name)."""

import os

import cv2
import numpy as np

import h5_layer
from common import assign
from g_bank import bank, render
from rows import find_tab
from textmask import Shadow

MAX_COST = float(os.environ.get("I2_MAX_COST", 0.45))
MARGIN = float(os.environ.get("I2_MARGIN", 0.08))
TOPF = int(os.environ.get("I2_TOPF", 3))
NPEAK = 3
DX = int(os.environ.get("I2_DX", 1))  # hits this close in x (same row) are one word
TEAMS = h5_layer.TEAMS


def phase(m: np.ndarray, k: int, axis: int) -> int:
    if k == 1:
        return 0
    a = np.moveaxis(m, axis, 1)
    e = a[:, 1:] & ~a[:, :-1]
    xs = np.nonzero(e.any(axis=0))[0] + 1
    w = e.sum(axis=0)[xs - 1]
    return int(np.bincount(xs % k, weights=w, minlength=k).argmax())


def font_px(rgb: np.ndarray, k: int, box: tuple[int, int, int, int] | None):
    """soft text mask, text colour and shadow colour per font px"""
    h, w, _ = rgb.shape
    y0, y1, x0, x1 = box or (0, h, 0, w)
    sh = Shadow(rgb).mask(k)[y0:y1, x0:x1]
    py, px = phase(sh, k, 0), phase(sh, k, 1)
    H, W = (sh.shape[0] - py) // k - 1, (sh.shape[1] - px) // k - 1
    s = sh[py : py + H * k, px : px + W * k].reshape(H, k, W, k).mean(axis=(1, 3)).astype(np.float32)
    cy, cx = y0 + py + k // 2, x0 + px + k // 2
    col = rgb[cy : cy + H * k : k, cx : cx + W * k : k]
    shd = rgb[cy + k : cy + (H + 1) * k : k, cx + k : cx + (W + 1) * k : k]
    return s, col[:H, :W], shd[:H, :W]


LETTER = {"R": "red", "B": "blue", "G": "green", "Y": "yellow", "A": "aqua", "P": "pink", "W": "white", "S": "gray"}
LET_MIN = float(os.environ.get("I2_LET_MIN", 0.6))
LET_MARGIN = float(os.environ.get("I2_LET_MARGIN", 0.05))
LET_CHECK = os.environ.get("I2_LET", "1") != "0"
LET_VETO = os.environ.get("I2_LET") == "veto"
VETO_COST = 1.0  # veto mode: a hit with no clear letter needs cost <= this


def letter_at(s: np.ndarray, f, y: int, x: int, th: int) -> str | None:
    """team of the best-matching (bold) team letter left of the name"""
    win = s[max(0, y - 1) : y + th + 1, max(0, x - 16) : x + 2]
    sc = {}
    for L, team in LETTER.items():
        best = -1.0
        for bold in (True, False):
            t = render(f, L, 1)
            if bold:
                t = np.concatenate([t, np.zeros((t.shape[0], 1), bool)], axis=1)
                t[:, 1:] |= t[:, :-1].copy()
            t = shadow_fix(t)
            p = np.zeros((t.shape[0] + 2, t.shape[1] + 2), np.float32)
            p[1:-1, 1:-1] = t
            if p.shape[0] > win.shape[0] or p.shape[1] > win.shape[1]:
                continue
            best = max(best, float(cv2.matchTemplate(win, p, cv2.TM_CCOEFF_NORMED).max()))
        sc[team] = best
    v = sorted(sc.values(), reverse=True)
    top = max(sc, key=sc.get)
    if v[0] < LET_MIN or v[0] - v[1] < LET_MARGIN:
        return None
    return top


def shadow_fix(t: np.ndarray) -> np.ndarray:
    d = np.zeros_like(t)
    d[:-1, :-1] = t[1:, 1:]
    return t & ~d


def template(f, name: str) -> np.ndarray:
    t = render(f, name, 1)
    # a text px whose shadow spot is text fails the shadow test
    d = np.zeros_like(t)
    d[:-1, :-1] = t[1:, 1:]
    t = t & ~d
    out = np.zeros((t.shape[0] + 2, t.shape[1] + 4), np.float32)
    out[1:-1, 2:-2] = t
    return out


def peaks(r: np.ndarray, n: int, tw: int) -> list[tuple[float, int, int]]:
    r = r.copy()
    out = []
    for _ in range(n):
        _, v, _, (x, y) = cv2.minMaxLoc(r)
        if v <= 0.2:
            break
        out.append((float(v), y, x))
        r[max(0, y - 4) : y + 5, max(0, x - tw // 2) : x + tw // 2 + 1] = -1
    return out


def team_at(col, shd, t: np.ndarray, y: int, x: int) -> str | None:
    th, tw = t.shape
    ys, xs = np.nonzero(t > 0)
    ys, xs = ys + y, xs + x
    ok = (ys < col.shape[0]) & (xs < col.shape[1])
    ys, xs = ys[ok], xs[ok]
    if len(ys) < 4:
        return None
    a = h5_layer.hue(col[ys, xs])
    b = h5_layer.hue(shd[ys, xs], 4)
    a = np.where(a >= 0, a, b)
    v = a[a >= 0]
    if len(v) < 0.5 * len(a):
        return None
    ti = np.bincount(v).argmax()
    if (v == ti).sum() < 0.6 * len(a):
        return None
    # the team letter: same colour text left of the name
    ly0, ly1 = y + 1, y + th - 1
    lx0, lx1 = max(0, x + 2 - 14), max(0, x + 2 - 2)
    pc = col[ly0:ly1, lx0:lx1].reshape(-1, 3)
    ps = shd[ly0:ly1, lx0:lx1].reshape(-1, 3)
    pa = h5_layer.hue(pc)
    pb = h5_layer.hue(ps, 4)
    bright = pc.max(axis=1) >= 60
    lt = np.where(pa >= 0, pa, pb)
    if ((lt == ti) & bright).sum() < 5:
        return None
    return TEAMS[ti]


def tab_box(rgb: np.ndarray):
    tab = find_tab(rgb)
    if tab is None or not tab.rows:
        return None, None
    k = tab.k
    h, w, _ = rgb.shape
    y0 = min(r.y for r in tab.rows) - 12 * k
    y1 = max(r.y for r in tab.rows) + 21 * k
    x0 = min(r.x0 for r in tab.rows) - 240 * k
    x1 = max(r.x1 for r in tab.rows) + 120 * k
    return k, (max(0, y0), min(h, y1), max(0, x0), min(w, x1))


def scores(s: np.ndarray, fonts, known: list[str]) -> dict:
    """{(font idx, name idx): result map}"""
    out = {}
    for fi in fonts:
        for j, n in enumerate(known):
            t = template(bank()[fi], n)
            if t.shape[0] > s.shape[0] or t.shape[1] > s.shape[1] or t.sum() < 4:
                continue
            out[fi, j] = (cv2.matchTemplate(s, t, cv2.TM_CCOEFF_NORMED), t)
    return out


def pick_fonts(s: np.ndarray, known: list[str]) -> list[int]:
    probe = sorted(range(len(known)), key=lambda j: -len(known[j]))[:4]
    pk = [known[j] for j in probe]
    fs = []
    for fi in range(len(bank())):
        r = scores(s, [fi], pk)
        v = sorted((m.max() for m, _ in r.values()), reverse=True)
        fs.append((float(np.mean(v)) if v else 0.0, fi))
    fs.sort(reverse=True)
    return [fi for _, fi in fs[:TOPF]]


def spot(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    if not known:
        return {}
    k, box = tab_box(rgb)
    ks = [k] if k else [kk for kk in (2, 1, 3, 4) if min(rgb.shape[0] // 240, rgb.shape[1] // 320) >= kk]
    best = None
    for kk in ks:
        s, col, shd = font_px(rgb, kk, box)
        fonts = pick_fonts(s, known)
        res = scores(s, fonts, known)
        tot = np.mean([max((res[fi, j][0].max() for fi in fonts if (fi, j) in res), default=0) for j in range(len(known))])
        if best is None or tot > best[0]:
            best = (tot, s, col, shd, fonts, res)
    _, s, col, shd, fonts, res = best
    # candidate hits: top peaks per name (best font)
    hits: list[tuple[int, int, str | None]] = []
    for j in range(len(known)):
        for fi in fonts:
            if (fi, j) not in res:
                continue
            r, t = res[fi, j]
            for v, y, x in peaks(r, NPEAK, t.shape[1]):
                if v < 1 - MAX_COST - MARGIN:
                    continue
                if any(abs(y - hy) <= 2 and abs(x - hx) <= DX for hy, hx, _ in hits):
                    continue
                hits.append((y, x, team_at(col, shd, t, y, x)))
    if not hits:
        return {}
    cost = np.ones((len(hits), len(known)))
    for i, (y, x, _) in enumerate(hits):
        for j in range(len(known)):
            for fi in fonts:
                if (fi, j) not in res:
                    continue
                r = res[fi, j][0]
                v = r[max(0, y - 1) : y + 2, max(0, x - DX) : x + DX + 1].max(initial=-1)
                cost[i, j] = min(cost[i, j], 1 - v)
    out = {}
    for i, j in assign(cost, MAX_COST, MARGIN):
        y, x, team = hits[i]
        if team is None:
            continue
        if LET_CHECK:
            th = template(bank()[fonts[0]], known[j]).shape[0]
            lt = letter_at(s, bank()[fonts[0]], y, x, th)
            # veto: only a clearly different letter rejects the hit
            if lt != team and (not LET_VETO or lt is not None or cost[i, j] > VETO_COST):
                continue
        out[known[j]] = team
    return out


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return spot(rgb, known)
