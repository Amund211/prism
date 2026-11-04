"""
Algorithm B: find tab rows in a blurred / scaled tab list.

Does not need exact pixels or a font:
1. Pixels near a team color (by color direction, so blur and shading are
   fine) -> segments per color.
2. Row = short segment (bold team letter) + name segment, same color. The
   letter is a capital: it gives cap line, baseline and GUI px size.
3. `decide`: one assignment of names to rows for the whole image
   (Hungarian). A name gets a team only if every solution with another team
   for it is clearly worse (margin). Row-name scores come from `learn.py`.
"""

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image
from scipy import ndimage  # type: ignore[import-untyped]
from scipy.optimize import linear_sum_assignment  # type: ignore[import-untyped]

from prism.overlay.tabshot.screenshot import Team
from prism.overlay.tabshot.teams.glyphs import Bitmap, render

# Channel pattern: 3 = high, 1 = a third
TEAMS: dict[Team, tuple[int, int, int]] = {
    "aqua": (1, 3, 3),
    "blue": (1, 1, 3),
    "green": (1, 3, 1),
    "pink": (3, 1, 3),
    "red": (3, 1, 1),
    "white": (3, 3, 3),
    "gray": (3, 3, 3),
    "yellow": (3, 3, 1),
}
TEAM_NAMES: list[Team] = list(TEAMS)
GRAY = TEAM_NAMES.index("gray")
WHITE = TEAM_NAMES.index("white")
LETTERS = dict(zip(TEAM_NAMES, "ABGPRWSY"))

MIN_LETTER = 0.4  # NCC of the team letter vs the generic bold letter
SCALE = 10.0  # score = SCALE * (ncc - 1)
MIN_SCORE = -6.0  # Below this a row-name pair is not allowed
MARGIN = 1.5  # Team decided only if the best other team scores this much less
# A row with no name (chat, HUD, cut-off row): just below MIN_SCORE. A
# strong match (~-3) keeps its margin; a weak best (~-6) does not.
# A name with no row costs 0: dead players are not in the list.
ROW_UNMATCHED = -7.0
GRAY_TOL = 16.0  # Gray text: v within this of 85 counts as (partly) text
# White text: v at least this. The tab background over bright sky is ~145
WHITE_MIN = 170

Array = npt.NDArray[Any]


@dataclass
class Seg:
    color: int
    x0: int
    x1: int
    y0: int
    y1: int


@dataclass
class SoftRow:
    team: Team
    x0: int  # Name x
    cap: int  # Cap line y
    base: int  # Baseline y (exclusive)
    ox: int  # Window origin
    oy: int
    alpha: Bitmap  # Window around the name: 0 = background, 1 = text
    lx: int  # Letter x
    # Cached by learn._row_weights
    weights: tuple[Array, Array, Array, float] | None = None


def classify(rgb: Array) -> Array:
    """Team index per pixel by color direction, -1 = none"""
    a = rgb.astype(np.int16)
    v = a.max(axis=2)
    # Per channel: high (>= 0.8 v) or low (<= 0.53 v, a third +- 0.2)
    hi = [a[..., c] * 5 >= v * 4 for c in range(3)]
    lo = [a[..., c] * 15 <= v * 8 for c in range(3)]
    valid = (hi[0] | lo[0]) & (hi[1] | lo[1]) & (hi[2] | lo[2])
    code = hi[0] * 4 + hi[1] * 2 + hi[2]
    lut = np.full(8, -1, dtype=np.int8)
    for i, pat in enumerate(TEAMS.values()):
        if i != GRAY:
            lut[(pat[0] == 3) * 4 + (pat[1] == 3) * 2 + (pat[2] == 3)] = i
    cls = np.where(valid, lut[code], -1).astype(np.int8)
    cls[(cls >= 0) & (cls != WHITE) & (v < 120)] = -1
    neutral = (cls == WHITE) | (valid & (code == 7))
    cls[(cls == WHITE) & (v < WHITE_MIN)] = -1
    # Gray team text: neutral (within ~0.12), dim. Stone fits too; the
    # letter check and the column filter remove it.
    tight = a.min(axis=2) * 100 >= v * 88
    cls[neutral & tight & (v >= 55) & (v < 115)] = GRAY
    return cls


def segments(cls: Array) -> list[Seg]:
    segs = []
    for i in range(len(TEAMS)):
        m = cls == i
        if not m.any():
            continue
        # Small gaps are bridged later, when pieces are chained into lines
        lab, _ = ndimage.label(m, structure=np.ones((3, 3)))
        for sl in ndimage.find_objects(lab):
            if sl is None:  # pragma: nocover
                continue
            ys, xs = sl
            segs.append(Seg(i, xs.start, xs.stop, ys.start, ys.stop))
    return segs


@dataclass
class _Line:
    segs: list[Seg]
    height: int


def _lines(segs: list[Seg]) -> list[list[Seg]]:
    """Same color, same text line, gaps < ~6 GUI px; sorted by x"""
    by_color: dict[int, list[Seg]] = {}
    for s in segs:
        by_color.setdefault(s.color, []).append(s)
    out: list[list[Seg]] = []
    for group in by_color.values():
        group.sort(key=lambda s: s.x0)
        # Sorted by x, so a line whose end is far left of this segment can
        # not grow any more
        open_lines: list[_Line] = []
        for s in group:
            h = s.y1 - s.y0
            still = []
            for line in open_lines:
                if s.x0 - line.segs[-1].x1 <= 0.9 * max(40, line.height):
                    still.append(line)
                else:
                    out.append(line.segs)
            open_lines = still
            for line in open_lines:
                lh = line.height
                l0, l1 = line.segs[0].y0, line.segs[0].y1
                if not (l0 - h <= s.y0 <= l1 + 1):
                    continue
                overlap = min(s.y1, l1) - max(s.y0, l0)
                # '_' and descenders: small piece just under the line
                under = l0 <= s.y0 <= l1 + 1 and h <= 0.4 * lh
                if s.x0 - line.segs[-1].x1 <= 0.9 * max(h, lh) and (
                    overlap >= 0.5 * min(h, l1 - l0) or under
                ):
                    line.segs.append(s)
                    line.height = max(lh, h)
                    break
            else:
                open_lines.append(_Line([s], h))
        out += [line.segs for line in open_lines]
    return out


def _pairs(segs: list[Seg]) -> list[tuple[Seg, Seg]]:
    """
    (letter, name): the letter is the piece before the first space.

    Pieces before it (skin head, Lunar icon) are ignored. The space is
    ~5 GUI px; gaps inside a blurred name are <= ~3 GUI px.
    """
    out = []
    for line in _lines(segs):
        if len(line) < 2:
            continue
        big = [s for s in line if s.y1 - s.y0 >= 4]
        if not big:
            continue
        h = max(s.y1 - s.y0 for s in big)
        cut = next(
            (
                k
                for k in range(len(line) - 1)
                if line[k + 1].x0 - line[k].x1 >= 0.55 * h
            ),
            None,
        )
        if cut is None:
            continue
        letter, rest = line[cut], line[cut + 1 :]
        lh, lw = letter.y1 - letter.y0, letter.x1 - letter.x0
        name = Seg(
            letter.color,
            rest[0].x0,
            max(s.x1 for s in rest),
            min(s.y0 for s in rest),
            max(s.y1 for s in rest),
        )
        if (
            lh >= 4
            and 0.5 * lh <= lw <= 1.2 * lh
            and rest[0].x0 - letter.x1 >= 0.2 * lh
            and name.x1 - name.x0 >= 1.5 * lh
            and letter.y0 <= name.y0 + 1
        ):
            out.append((letter, name))
    return out


def _column(pairs: list[tuple[Seg, Seg]]) -> list[tuple[Seg, Seg]]:
    """The biggest group of letters at about the same x"""
    best: list[tuple[Seg, Seg]] = []
    for letter, _ in pairs:
        u = (letter.y1 - letter.y0) / 7
        # Lunar puts an icon before some letters: allow ~10 GUI px right
        group = [(a, b) for a, b in pairs if -2 * u <= a.x0 - letter.x0 <= 10 * u]
        if len(group) > len(best):
            best = group
    return best


def _columns(pairs: list[tuple[Seg, Seg]]) -> list[tuple[Seg, Seg]]:
    """
    Tab rows: the biggest column, plus columns next to it on the same row grid.

    More than 20 rows (e.g. npc rows at game start) split the list into
    columns. The scoreboard is too far right and not on the grid.
    """
    best = _column(pairs)
    if not best:
        return best
    u = float(np.median([(a.y1 - a.y0) / 7 for a, _ in best]))
    pitch, cap0 = 9 * u, min(a.y0 for a, _ in best)
    xs = [min(a.x0 for a, _ in best)]
    out = list(best)
    rest = [p for p in pairs if p not in best]
    while len(group := _column(rest)) >= 2:
        rest = [p for p in rest if p not in group]
        x = min(a.x0 for a, _ in group)
        k = [(a.y0 - cap0) / pitch for a, _ in group]
        if 40 * u <= min(abs(x - x2) for x2 in xs) <= 180 * u and all(
            abs(v - round(v)) <= 0.25 for v in k
        ):
            xs.append(x)
            out += group
    return out


def find_rows(rgb: Array, cls: Array) -> list[SoftRow]:
    pairs = _pairs(segments(cls))
    pairs = _columns(
        [(lt, n) for lt, n in pairs if letter_score(cls, lt) >= MIN_LETTER]
    )
    rows = []
    for letter, n in pairs:
        # Window: the name, a bit around it, room for a cut-off end
        x1 = n.x1 + max(4, (n.x1 - n.x0) // 3)
        rows.append(make_row(rgb, n.color, letter.y0, letter.y1, letter.x0, n.x0, x1))
    return rows


def make_row(
    rgb: Array, color: int, cap: int, base: int, lx: int, x0: int, x1: int
) -> SoftRow:
    """A row of this color at this place"""
    h, w = rgb.shape[:2]
    u = (base - cap) / 7
    oy, ox = max(0, cap - 2), max(0, x0 - 2)
    y1 = min(h, cap + math.ceil(8 * u) + 2)
    alpha = _alpha(rgb[oy:y1, ox : min(w, x1)], color)
    return SoftRow(TEAM_NAMES[color], x0, cap, base, ox, oy, alpha, lx)


def _alpha(win: Array, color: int) -> Bitmap:
    """How much of each pixel is text of this color (blur mixes it)"""
    if color == GRAY:
        # Gray text (0x555555) can be darker than the background, so use
        # the distance to the text color, not brightness
        a = win.astype(np.float32)
        v = a.max(axis=2)
        neutral = a.min(axis=2) >= 0.88 * v
        near: Bitmap = (np.clip(1 - np.abs(v - 85) / GRAY_TOL, 0, 1) * neutral).astype(
            np.float32
        )
        return near
    t = np.array(TEAMS[TEAM_NAMES[color]], dtype=np.float32) * 85
    proj = win.astype(np.float32) @ t / float(t @ t)
    bg = float(np.percentile(proj, 30))
    alpha: Bitmap = np.clip((proj - bg) / max(1e-3, 1 - bg), 0, 1).astype(np.float32)
    return alpha


@lru_cache(maxsize=256)
def _bold(ch: str, u: float) -> Bitmap:
    """Bold capital (drawn twice, 1 GUI px apart), rows 0-6, scaled"""
    g = render(ch)[:7]
    b = np.zeros((7, g.shape[1] + 1), dtype=np.float32)
    b[:, :-1] = g
    b[:, 1:] = np.maximum(b[:, 1:], g)
    w, h = max(1, round(b.shape[1] * u)), max(1, round(7 * u))
    im = Image.fromarray((b * 255).astype(np.uint8)).resize(
        (w, h), Image.Resampling.BOX
    )
    return (np.asarray(im, dtype=np.float32) / 255).astype(np.float32)


def ncc(a: Array, b: Array) -> float:
    """Normalized cross-correlation"""
    a = a - a.mean()
    b = b - b.mean()
    d = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum()) / d if d > 0 else 0.0


def letter_score(cls: Array, letter: Seg) -> float:
    """How well the letter segment looks like its team's bold letter"""
    u = round((letter.y1 - letter.y0) / 7, 2)
    p = _bold(LETTERS[TEAM_NAMES[letter.color]], u)
    ph, pw = p.shape
    best = -1.0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            y, x = letter.y0 + dy, letter.x0 + dx
            if y < 0 or x < 0 or y + ph > cls.shape[0] or x + pw > cls.shape[1]:
                continue
            obs = (cls[y : y + ph, x : x + pw] == letter.color).astype(np.float32)
            best = max(best, ncc(p, obs))
    return best


def _assign(S: Array) -> tuple[float, dict[int, int]]:
    """Best total; rows / names may stay unmatched"""
    nr, nn = S.shape
    big = np.zeros((nr + nn, nn + nr), dtype=float)
    big[:nr, :nn] = np.where(S >= MIN_SCORE, S, -1e6)
    big[:nr, nn:] = ROW_UNMATCHED
    ri, ci = linear_sum_assignment(-big)
    total = float(big[ri, ci].sum())
    return total, {
        int(r): int(c) for r, c in zip(ri, ci) if r < nr and c < nn and big[r, c] > -1e5
    }


def decide(
    rows: list[SoftRow],
    names: list[str],
    S: Array,
    fixed: dict[str, Team],
) -> dict[str, int]:
    """{name: row index} for names whose team is clear, from scores S"""
    S = S.copy()
    for j, n in enumerate(names):
        if n in fixed:  # A known team: only rows of that team, bonus
            for i, r in enumerate(rows):
                S[i, j] = S[i, j] + 5 if r.team == fixed[n] else -1e6
    total, a = _assign(S)

    out = {}
    for i, j in a.items():
        team = rows[i].team
        # Best solution where this name is not in this team
        S2 = S.copy()
        for k, r in enumerate(rows):
            if r.team == team:
                S2[k, j] = -1e6
        alt, _ = _assign(S2)
        if total - alt >= MARGIN:
            out[names[j]] = i
    return out
