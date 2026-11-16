"""i5: recall. Second text mask (palette colours, overlay un-blend) merged
with the shadow mask, then the normal ladder row finder on the union."""

import cv2
import numpy as np

import common
from common import PRow, find_letter, team_of, word_gap
from rows import Tab, find_rows_k, find_tab
from rowparse import Word, nearest_team, row_text, words
from textmask import Shadow

# team colours + light gray (respawning) + the faint-edge variant (x 0.988)
_PAL = np.array(
    [(255, 85, 85), (85, 85, 255), (85, 255, 85), (255, 255, 85), (85, 255, 255), (255, 255, 255),
     (255, 85, 255), (170, 170, 170)], np.int16)


def palette_mask(px: np.ndarray, tol: int = 12) -> np.ndarray:
    """Pixels near a palette colour (also x 0.988: tc16). No shadow needed."""
    p = px.astype(np.int16)
    m = np.zeros(px.shape[:2], bool)
    for c in _PAL:
        for s in (1.0, 0.988):
            m |= (np.abs(p - (c * s).astype(np.int16)).max(axis=2) <= tol)
    return m


def overlay_params(px: np.ndarray, k: int) -> tuple[np.ndarray, float] | None:
    """Blend obs = aC + s T over the text. Text pixel p and its shadow q
    (T/4) give aC = (4q - p) / 3 for every text pixel; s from p - aC."""
    p = px[:-k, :-k].astype(np.int32)
    q = px[k:, k:].astype(np.int32)
    d = p - q
    ok = (d.min(axis=2) >= 4) & (p.max(axis=2) >= 24)
    if ok.sum() < 200:
        return None
    ac = (4 * q[ok] - p[ok]) / 3.0
    key = np.round(ac / 3).astype(np.int32)
    keys, cnt = np.unique(key[:, 0] * 10000 + key[:, 1] * 100 + key[:, 2], return_counts=True)
    best = None
    for kk, c in sorted(zip(keys, cnt), key=lambda t: -t[1])[:6]:
        a0 = np.array([kk // 10000, (kk // 100) % 100, kk % 100]) * 3.0
        sel = np.abs(ac - a0).max(axis=1) <= 4
        s = (p[ok][sel].max(axis=1) - a0.max()) / 255.0
        hist, edges = np.histogram(s, bins=20, range=(0.05, 0.85))
        i = int(hist.argmax())
        if hist[i] >= 60 and edges[i] < 0.7 and (best is None or hist[i] > best[2]):
            best = (a0, float(edges[i] + 0.02), int(hist[i]))
    return None if best is None else (best[0], best[1])


def find_tab_i5(rgb: np.ndarray, unblend: bool = True, pal: bool = True,
                tab: Tab | None = None) -> tuple[Tab | None, np.ndarray]:
    tab = tab or find_tab(rgb)
    if tab is None or not tab.rows:
        return tab, rgb
    k = tab.k
    H, W = rgb.shape[:2]
    tops = [r.y for r in tab.rows]
    y0, y1 = max(0, min(tops) - 9 * k), min(H, max(tops) + 18 * k)
    x0 = max(0, min(r.x0 for r in tab.rows) - 140 * k)
    x1 = min(W, max(r.x1 for r in tab.rows) + 40 * k)
    reg = rgb[y0:y1, x0:x1]
    aux = np.zeros(reg.shape[:2], bool)
    rgb2 = rgb
    if pal:
        # some darker pixel at (+k, +k): not flat bright areas (snow, sky)
        pm = palette_mask(reg)
        v = reg.max(axis=2).astype(np.int16)
        dark = np.zeros_like(pm)
        dark[:-k, :-k] = v[k:, k:] * 4 <= v[:-k, :-k] * 3
        # coloured palette pixels are rare in scenes; white / gray need it
        sat = (reg.max(axis=2).astype(np.int16) - reg.min(axis=2)) >= 120
        aux |= pm & (dark | sat)
    if unblend:
        par = overlay_params(reg, k)
        if par is not None:
            ac, s = par
            u = np.clip((reg.astype(np.float32) - ac) / s, 0, 255).astype(np.uint8)
            dim = reg.max(axis=2) <= 255 * s + ac.max() + 12
            # un-blended text must be a palette colour (else noise / AA edges)
            um = Shadow(u).mask(k) & dim & palette_mask(u, tol=16)
            if um.sum() >= 50:
                aux |= um
                grow = cv2.dilate(um.astype(np.uint8), np.ones((k + 2, k + 2), np.uint8)).astype(bool)
                rgb2 = rgb.copy()
                rgb2[y0:y1, x0:x1][grow] = u[grow]
    m = tab.mask.copy()
    m[y0:y1, x0:x1] |= aux
    rows2, real2 = find_rows_k(m, k)
    if real2 < tab.real or len(rows2) < len(tab.rows):
        return tab, rgb
    return Tab(k, rows2, m, real2), rgb2


def prev_letter(ws: list[Word], name: Word, k: int) -> Word | None:
    """The word just before the name is one glyph in the name colour, at a
    gap < 3k (narrow-spaced fonts: find_letter wants >= 3k)"""
    i = next((i for i, w in enumerate(ws) if w is name), 0)
    if i == 0:
        return None
    w = ws[i - 1]
    ok = len(w.spans) <= 2 and 2 * k <= w.x1 - w.x0 <= 8 * k and k <= name.x0 - w.x1 < 6 * k
    if ok and max(abs(a - b) for a, b in zip(w.color, name.color)) <= 24:
        return w
    return None


def split_letter(w: Word, k: int) -> tuple[Word, Word] | None:
    """Letter merged into the name word (tight letter spacing fonts)"""
    sp = w.spans
    if len(sp) < 4:
        return None
    g = [b[0] - a[1] for a, b in zip(sp, sp[1:])]
    w0 = sp[0][1] - sp[0][0]
    rest = sorted(g[1:])
    if not (2 * k <= w0 <= 8 * k) or g[0] < 2 * k or g[0] < 1.6 * rest[len(rest) // 2] or g[0] <= max(g[1:]):
        return None
    off = sp[1][0] - w.x0
    letter = Word(sp[0][0], sp[0][1], [sp[0]], w.color, w.shadow, w.mask[:, : sp[0][1] - w.x0])
    name = Word(sp[1][0], w.x1, sp[1:], w.color, w.shadow, w.mask[:, off:])
    return letter, name


def parse(rgb: np.ndarray, unblend: bool = True, pal: bool = True, split: bool = True,
          wide: bool = True) -> tuple[Tab | None, list[PRow]]:
    """Base parse (shadow mask); then rows from the aux-mask parse fill in
    the y bands where the base parse has no team row"""
    base_tab = find_tab(rgb)
    if base_tab is None:
        return None, []
    tab, base = _parse_on(rgb, base_tab, split, wide)
    if not (unblend or pal):
        return tab, base
    tab2, rgb2 = find_tab_i5(rgb, unblend, pal, base_tab)
    if tab2 is base_tab:
        return tab, base
    _, aux = _parse_on(rgb2, tab2, split, wide)
    k = tab.k
    have = [p.row.y for p in base if p.team]
    out = list(base)
    for p in aux:
        if p.team and all(abs(p.row.y - y) > 2 * k for y in have):
            out = [q for q in out if abs(q.row.y - p.row.y) > 2 * k or q.row.col != p.row.col]
            out.append(p)
            have.append(p.row.y)
    out.sort(key=lambda p: (p.row.col, p.row.y))
    return tab, out


def _parse_on(rgb2: np.ndarray, tab: Tab, split: bool, wide: bool) -> tuple[Tab, list[PRow]]:
    out = []
    k = tab.k
    rts = [row_text(rgb2, tab.mask, r) for r in tab.rows]
    gap = word_gap([rt for rt in rts if rt], k)
    for r, rt in zip(tab.rows, rts):
        ws = words(rgb2, tab.mask, r, gap=gap, rt=rt) if rt else []
        if not ws:
            continue
        name = next((w for w in ws if len(w.spans) >= 3 and w.x1 - w.x0 >= 9 * k), None)
        letter = find_letter(rgb2, r, name, reach=7 + 2 * gap) if name else None
        if name and letter is None and split:
            letter = prev_letter(ws, name, k)
            sl = split_letter(name, k) if letter is None else None
            if sl:
                i = next(i for i, w in enumerate(ws) if w is name)
                letter, name = sl
                ws = ws[:i] + [letter, name] + ws[i + 1 :]
        team = team_of(name) if letter and name else None
        if team is None and letter and name and wide:
            team = nearest_team(name.color, max_dist=100)
        out.append(PRow(r, letter, name, team, ws))
    lg = [p.name.x0 - p.letter.x1 for p in out if p.letter and p.name]
    if len(lg) >= 3:
        med = float(np.median(lg))
        for p in out:
            if p.letter and p.name and abs(p.name.x0 - p.letter.x1 - med) > 2.5 * k:
                p.letter, p.team = None, None
    return tab, out


def install() -> None:
    """Make matchers that import common.parse use this parse"""
    import importlib

    for mod in ("common", "h_common", "h4_union", "g_match", "c_feats", "d_core"):
        importlib.import_module(mod).parse = parse
    common.parse = parse
