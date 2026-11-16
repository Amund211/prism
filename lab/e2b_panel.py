"""E2b: RapidOCR det + rec on the tab-panel crop. Team from the OCR'd team
letter, checked against the colour of the line's pixels. Does not use the
row parser's words (only the row finder, for the crop and scale)."""

import cv2
import numpy as np

from e2_rapidocr import engine
from e_ocrcommon import match
from rowparse import LETTER, PALETTE
from rows import find_tab

MAX_COST, MARGIN = 0.45, 0.1
BY_LETTER = {v: k for k, v in LETTER.items()}


def crop_box(rgb: np.ndarray) -> tuple[int, int, int, int, int]:
    """(x0, y0, x1, y1, k) around the found tab rows, with room for missed rows"""
    tab = find_tab(rgb)
    h, w, _ = rgb.shape
    if tab is None or not tab.rows:
        return 0, 0, w, h, 2
    k = tab.k
    x0 = min(r.x0 for r in tab.rows) - 40 * k
    x1 = max(r.x1 for r in tab.rows) + 40 * k
    y0 = min(r.y for r in tab.rows) - 4 * 9 * k
    y1 = max(r.y for r in tab.rows) + 6 * 9 * k
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1), k


def line_team(px: np.ndarray) -> str | None:
    """Palette team of the brightest frequent saturated colour in a box"""
    flat = px.reshape(-1, 3)
    v = flat.max(axis=1)
    flat = flat[v >= 72]
    if len(flat) == 0:
        return None
    vals, counts = np.unique(flat, axis=0, return_counts=True)
    keep = counts >= max(3, counts.max() // 4)
    vals = vals[keep]
    best, bd = None, 1e9
    for c in vals:
        for t, p in PALETTE.items():
            d = float(np.abs(c.astype(int) - np.array(p)).max())
            if d < bd:
                best, bd = t, d
    return best if bd <= 30 else None


def read_lines(rgb: np.ndarray) -> list[tuple[str, str | None, str | None]]:
    """(name text, letter team, colour team) per OCR line"""
    x0, y0, x1, y1, k = crop_box(rgb)
    crop = np.ascontiguousarray(rgb[y0:y1, x0:x1])
    f = max(1, round(4 / k))
    big = cv2.resize(crop, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST) if f > 1 else crop
    r = engine()(big, use_det=True, use_cls=False, use_rec=True)
    out = []
    if r.boxes is None:
        return out
    for box, txt in zip(r.boxes, r.txts):
        toks = [t for t in txt.replace("|", " ").split() if t]
        if not toks:
            continue
        letter = None
        if len(toks) >= 2 and len(toks[0]) == 1 and toks[0].upper() in BY_LETTER:
            letter = BY_LETTER[toks[0].upper()]
            toks = toks[1:]
        name = "".join(c for c in toks[0] if c.isalnum() or c == "_")
        bx = (np.asarray(box) / f).astype(int)
        bx0, by0 = bx.min(axis=0)
        bx1, by1 = bx.max(axis=0)
        px = crop[max(0, by0) : by1, max(0, bx0) : bx1]
        out.append((name, letter, line_team(px) if px.size else None))
    return out


def decide(letter: str | None, color: str | None) -> str | None:
    if letter is None:
        return None  # no letter: respawning / spectator / npc / not a row
    if color is None or color == letter:
        return letter
    return None


def read_texts(rgb: np.ndarray) -> tuple[list[str], list[str | None]]:
    lines = read_lines(rgb)
    return [n for n, _, _ in lines], [decide(lt, c) for _, lt, c in lines]


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    texts, teams = read_texts(rgb)
    return match(texts, teams, known, MAX_COST, MARGIN)
