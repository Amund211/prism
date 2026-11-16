"""E2c: RapidOCR rec on each full tab row band (row finder only, plus rows
extrapolated at the 9k pitch to fill gaps). The line text is aligned to each
known name (rapidfuzz partial alignment); the char before the name is the team
letter. Team = OCR letter, checked against the line colour."""

import cv2
import numpy as np
from rapidfuzz import fuzz

from common import assign
from e2_rapidocr import engine
from e2b_panel import BY_LETTER
from rowparse import PALETTE
from rows import find_tab
from textmask import shadow_mask

MAX_COST, MARGIN = 0.4, 0.1
LOOKALIKE = {"6": "G", "8": "B", "5": "S", "4": "A", "$": "S"}


def bands(rgb: np.ndarray) -> list[tuple[int, int, int, int]]:
    """(y, x0, x1, k) per row, gaps filled, one extra row above / below"""
    tab = find_tab(rgb)
    if tab is None or not tab.rows:
        return []
    k = tab.k
    p = 9 * k
    out = []
    cols: dict[int, list] = {}
    for r in tab.rows:
        cols.setdefault(r.col, []).append(r)
    for rs in cols.values():
        x0 = min(r.x0 for r in rs) - 4 * k
        x1 = max(r.x1 for r in rs) + 2 * k
        base = rs[0].y
        idx = sorted({round((r.y - base) / p) for r in rs})
        for i in range(idx[0] - 1, idx[-1] + 2):
            y = base + i * p
            if 0 <= y and y + 8 * k <= rgb.shape[0]:
                out.append((y, max(0, x0), min(rgb.shape[1], x1), k))
    return out


def ocr_band(rgb: np.ndarray, y: int, x0: int, x1: int, k: int) -> str:
    band = np.ascontiguousarray(rgb[max(0, y - k) : y + 9 * k, x0:x1])
    f = 5 / k
    big = cv2.resize(band, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST)
    r = engine()(big, use_det=False, use_cls=False, use_rec=True)
    return "".join(r.txts or ())


def text_team(rgb: np.ndarray, y: int, x0: int, x1: int, k: int) -> str | None:
    """Team colour of the shadowed text pixels in the left 60 % of the row
    (the score is yellow, at the right). Gray only if no other colour."""
    sub = rgb[y : y + 9 * k, x0 : x1 + k]
    m = shadow_mask(sub, k)[: 8 * k, : x1 - x0]
    px = sub[: 8 * k, : x1 - x0][m]
    xs = np.nonzero(m)[1]
    px = px[xs < (x1 - x0) * 3 // 5].astype(int)
    if len(px) < 4 * k:
        return None
    counts = {t: int((np.abs(px - np.array(c)).max(axis=1) <= 30).sum()) for t, c in PALETTE.items()}
    best = max((t for t in counts if t != "gray"), key=lambda t: counts[t])
    if counts[best] >= max(4 * k, 0.3 * len(px)):
        return best
    if counts["gray"] >= 0.5 * len(px):
        return "gray"
    return None


def read_lines(rgb: np.ndarray) -> list[tuple[str, str | None]]:
    """(line text, colour team) per band"""
    out = []
    for y, x0, x1, k in bands(rgb):
        t = ocr_band(rgb, y, x0, x1, k)
        if not t.strip():
            continue
        out.append((t, text_team(rgb, y, x0, x1, k)))
    return out


NOT_ROWS = ("hypixel", "kills", "ranks", "playing", "boosters", "broken")


def score(name: str, line: str) -> tuple[float, str | None]:
    """(similarity 0..1, letter team) of the name inside the line"""
    line = line.replace(" ", "")
    low = line.lower()
    if any(w in low for w in NOT_ROWS):
        return 0.0, None
    al = fuzz.partial_ratio_alignment(name.lower(), low)
    if al is None:
        return 0.0, None
    s = al.score / 100
    # the found part should be about as long as the name
    s *= min(1.0, (al.dest_end - al.dest_start) / max(1, len(name)))
    pre = line[: al.dest_start].replace(" ", "")
    letter = BY_LETTER.get(LOOKALIKE.get(pre[-1], pre[-1]).upper()) if pre else None
    if len(pre) > 3:
        return 0.0, None  # the name starts the row (after head / letter / icons)
    if letter is None and pre:
        letter = "?"  # some glyph before the name: a letter OCR could not read
    return s, letter


def read_texts(rgb: np.ndarray):  # type: ignore[no-untyped-def]
    lines = read_lines(rgb)
    return [t for t, _ in lines], [c for _, c in lines]


def match_all(texts: list[str], colors: list[str | None], known: list[str],
              max_cost: float = MAX_COST, margin: float = MARGIN) -> dict[str, str | None]:
    """{name: team or None} for every name found in a line (None: no letter)"""
    if not texts or not known:
        return {}
    pairs = list(dict.fromkeys(zip(texts, colors)))
    sc = [[score(n, t) for n in known] for t, _ in pairs]
    cost = np.array([[1 - s for s, _ in row] for row in sc])
    out: dict[str, str | None] = {}
    for i, j in assign(cost, max_cost, margin):
        letter = sc[i][j][1]
        color = pairs[i][1]
        team = None
        if letter == "?":
            team = color
        elif letter and (color is None or color == letter):
            team = letter
        out[known[j]] = team if letter or team else None
        if letter and not team:
            out[known[j]] = "?"  # letter, but no sure team
    return out


def match_lines(texts: list[str], colors: list[str | None], known: list[str],
                max_cost: float = MAX_COST, margin: float = MARGIN) -> dict[str, str]:
    m = match_all(texts, colors, known, max_cost, margin)
    return {n: t for n, t in m.items() if t and t != "?"}


def read_all(rgb: np.ndarray, known: list[str]) -> dict[str, str | None]:
    texts, colors = read_texts(rgb)
    return match_all(texts, colors, known)


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    texts, colors = read_texts(rgb)
    return match_lines(texts, colors, known)
