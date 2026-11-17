"""Algorithm B: read Bedwars teams from a blurred / scaled tab list.

Does not need exact pixels or a font. Steps:
1. Pixels near a team color (by color direction, so blur and shading are
   fine) -> horizontal segments per color.
2. Row = short segment (bold team letter) + name segment, same color. The
   letter is a capital: it gives cap line, baseline and GUI px size.
3. Render each known name with a generic 5x7 pixel font (glyphs.py, not
   the user's font), area-scale it to the row's GUI px size, and compare
   with the row's ink (normalized cross-correlation, small shifts and
   width stretches).
4. One assignment of names to rows for the whole image (Hungarian). A
   name gets a team only if every solution with another team for it is
   clearly worse (margin).
5. Context (deduce): with the full roster, fill the last open team
   slots.
"""

import math
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glyphs import render  # noqa: E402

TEAMS = {
    "aqua": (1, 3, 3), "blue": (1, 1, 3), "green": (1, 3, 1),
    "pink": (3, 1, 3), "red": (3, 1, 1), "white": (3, 3, 3),
    "gray": (3, 3, 3), "yellow": (3, 3, 1),
}  # channel pattern: 3 = high, 1 = a third
TEAM_NAMES = list(TEAMS)
GRAY = TEAM_NAMES.index("gray")
WHITE = TEAM_NAMES.index("white")
EIGHT_TEAMS = TEAM_NAMES
FOUR_TEAMS = ["red", "blue", "green", "yellow"]

MIN_LETTER = 0.4  # NCC of the team letter vs the generic bold letter
STRETCHES = (0.9, 1.0, 1.1)  # pack fonts are a bit wider / narrower
SCALE = 10.0  # score = SCALE * (ncc - 1)
MIN_SCORE = -6.0  # below this a row-name pair is not allowed
MARGIN = 1.5  # team decided only if the best other team scores this much less
# A row with no name (chat, HUD, cut-off row): just below MIN_SCORE. A
# strong match (~-3) keeps its margin; a weak best (~-6) does not.
ROW_UNMATCHED = -7.0
# A name with no row costs 0: dead players are not in the list.


@dataclass
class Seg:
    color: int
    x0: int
    x1: int
    y0: int
    y1: int


@dataclass
class SoftRow:
    team: str
    x0: int
    x1: int
    cap: int  # cap line y
    base: int  # baseline y (exclusive)
    ink: np.ndarray  # team-color mask around the name
    ox: int  # ink window origin
    oy: int
    alpha: np.ndarray | None = None  # same window: 0 = background, 1 = text
    lx: int = -1  # letter x


def classify(rgb: np.ndarray) -> np.ndarray:
    """Team index per pixel by color direction, -1 = none."""
    a = rgb.astype(np.int16)
    v = a.max(axis=2)
    # Per channel: high (>= 0.8 v) or low (<= 0.53 v, a third +- 0.2).
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
    cls[(cls == WHITE) & (v < 140)] = -1
    # Gray team text: neutral (within ~0.12), dim. Stone fits too; the
    # letter check and the column filter remove it.
    tight = a.min(axis=2) * 100 >= v * 88
    cls[neutral & tight & (v >= 55) & (v < 115)] = GRAY
    return cls


def segments(cls: np.ndarray, gap: int) -> list[Seg]:
    segs = []
    for i in range(len(TEAMS)):
        m = cls == i
        if not m.any():
            continue
        # Small gaps are bridged later, when pieces are chained into lines.
        lab, _ = ndimage.label(m, structure=np.ones((3, 3)))
        for sl in ndimage.find_objects(lab):
            if sl is None:
                continue
            ys, xs = sl
            segs.append(Seg(i, xs.start, xs.stop, ys.start, ys.stop))
    return segs


def _lines(segs: list[Seg]) -> list[list[Seg]]:
    """Same color, same text line, gaps < ~6 GUI px; sorted by x."""
    by_color: dict[int, list[Seg]] = {}
    for s in segs:
        by_color.setdefault(s.color, []).append(s)
    out: list[list[Seg]] = []
    for group in by_color.values():
        group.sort(key=lambda s: s.x0)
        # Open lines: [segs, max height]. Sorted by x, so a line whose end
        # is far left of this segment can not grow any more.
        open_lines: list[list] = []
        for s in group:
            h = s.y1 - s.y0
            still = []
            for line in open_lines:
                if s.x0 - line[0][-1].x1 <= 0.9 * max(40, line[1]):
                    still.append(line)
                else:
                    out.append(line[0])
            open_lines = still
            for line in open_lines:
                segs, lh = line
                l0, l1 = segs[0].y0, segs[0].y1
                if not (l0 - h <= s.y0 <= l1 + 1):
                    continue
                overlap = min(s.y1, l1) - max(s.y0, l0)
                # '_' and descenders: small piece just under the line.
                under = l0 <= s.y0 <= l1 + 1 and h <= 0.4 * lh
                if s.x0 - segs[-1].x1 <= 0.9 * max(h, lh) and (
                    overlap >= 0.5 * min(h, l1 - l0) or under
                ):
                    segs.append(s)
                    line[1] = max(lh, h)
                    break
            else:
                open_lines.append([[s], h])
        out += [line[0] for line in open_lines]
    return out


def _pairs(segs: list[Seg]) -> list[tuple[Seg, Seg]]:
    """(letter, name): the letter is the piece before the first space.

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
            (k for k in range(len(line) - 1) if line[k + 1].x0 - line[k].x1 >= 0.55 * h),
            None,
        )
        if cut is None:
            continue
        l, rest = line[cut], line[cut + 1 :]
        lh, lw = l.y1 - l.y0, l.x1 - l.x0
        name = Seg(l.color, rest[0].x0, max(s.x1 for s in rest),
                   min(s.y0 for s in rest), max(s.y1 for s in rest))
        if (
            lh >= 4
            and 0.5 * lh <= lw <= 1.2 * lh
            and rest[0].x0 - l.x1 >= 0.2 * lh
            and name.x1 - name.x0 >= 1.5 * lh
            and l.y0 <= name.y0 + 1
        ):
            out.append((l, name))
    return out


def _column(pairs: list[tuple[Seg, Seg]]) -> list[tuple[Seg, Seg]]:
    """Tab rows: the biggest group of letters at about the same x."""
    best: list[tuple[Seg, Seg]] = []
    for l, _ in pairs:
        u = (l.y1 - l.y0) / 7
        # Lunar puts an icon before some letters: allow ~10 GUI px right.
        group = [(a, b) for a, b in pairs if -2 * u <= a.x0 - l.x0 <= 10 * u]
        if len(group) > len(best):
            best = group
    return best


def find_rows(rgb: np.ndarray) -> list[SoftRow]:
    cls = classify(rgb)
    pairs = _pairs(segments(cls, 1))
    pairs = _column([(l, n) for l, n in pairs if letter_score(cls, l) >= MIN_LETTER])
    rows = []
    h, w = cls.shape
    for l, n in pairs:
        cap, base = l.y0, l.y1
        u = (base - cap) / 7
        # Window: the name, a bit around it, room for a cut-off end.
        oy, ox = max(0, cap - 2), max(0, n.x0 - 2)
        y1 = min(h, cap + math.ceil(8 * u) + 2)
        x1 = min(w, n.x1 + max(4, (n.x1 - n.x0) // 3))
        ink = (cls[oy:y1, ox:x1] == n.color).astype(np.float32)
        alpha = _alpha(rgb[oy:y1, ox:x1], n.color)
        rows.append(
            SoftRow(TEAM_NAMES[n.color], n.x0, n.x1, cap, base, ink, ox, oy, alpha, l.x0)
        )
    return rows


def make_row(
    rgb: np.ndarray, cls: np.ndarray, color: int, cap: int, base: int,
    lx: int, x0: int, x1: int,
) -> SoftRow:
    """A row at a known place (used by the grid in tablayout.py)."""
    h, w = cls.shape
    u = (base - cap) / 7
    oy, ox = max(0, cap - 2), max(0, x0 - 2)
    y1 = min(h, cap + math.ceil(8 * u) + 2)
    x1 = min(w, x1)
    ink = (cls[oy:y1, ox:x1] == color).astype(np.float32)
    alpha = _alpha(rgb[oy:y1, ox:x1], color)
    return SoftRow(TEAM_NAMES[color], x0, x1, cap, base, ink, ox, oy, alpha, lx)


def _alpha(win: np.ndarray, color: int) -> np.ndarray:
    """How much of each pixel is text of this color (blur mixes it)."""
    t = np.array(TEAMS[TEAM_NAMES[color]], dtype=np.float32) * 85
    if color == GRAY:
        t = np.full(3, 85, dtype=np.float32)
    proj = win.astype(np.float32) @ t / float(t @ t)
    bg = float(np.percentile(proj, 30))
    return np.clip((proj - bg) / max(1e-3, 1 - bg), 0, 1).astype(np.float32)


LETTERS = dict(zip(TEAM_NAMES, "ABGPRWSY"))


@lru_cache(maxsize=256)
def _bold(ch: str, u: float) -> np.ndarray:
    """Bold capital (drawn twice, 1 GUI px apart), rows 0-6, scaled."""
    g = render(ch)[:7]
    b = np.zeros((7, g.shape[1] + 1), dtype=np.float32)
    b[:, :-1] = g
    b[:, 1:] = np.maximum(b[:, 1:], g)
    w, h = max(1, round(b.shape[1] * u)), max(1, round(7 * u))
    im = Image.fromarray((b * 255).astype(np.uint8)).resize((w, h), Image.BOX)
    return np.asarray(im, dtype=np.float32) / 255


def letter_score(cls: np.ndarray, l: Seg) -> float:
    """How well the letter segment looks like its team's bold letter."""
    u = round((l.y1 - l.y0) / 7, 2)
    p = _bold(LETTERS[TEAM_NAMES[l.color]], u)
    ph, pw = p.shape
    best = -1.0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            y, x = l.y0 + dy, l.x0 + dx
            if y < 0 or x < 0 or y + ph > cls.shape[0] or x + pw > cls.shape[1]:
                continue
            obs = (cls[y : y + ph, x : x + pw] == l.color).astype(np.float32)
            best = max(best, _ncc(p, obs))
    return best


@lru_cache(maxsize=4096)
def _pred(name: str, u: float, stretch: float) -> np.ndarray:
    """Name rendered with the generic font, area-scaled to screen px."""
    bm = render(name)
    w = max(1, round(bm.shape[1] * u * stretch))
    h = max(1, round(8 * u))
    im = Image.fromarray((bm * 255).astype(np.uint8)).resize((w, h), Image.BOX)
    return np.asarray(im, dtype=np.float32) / 255


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    d = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum()) / d if d > 0 else 0.0


def score(row: SoftRow, name: str) -> float:
    """0 = perfect, more negative = worse. Best over small shifts / widths."""
    u = (row.base - row.cap) / 7
    best = -1.0
    for stretch in STRETCHES:
        p = _pred(name, round(u, 2), stretch)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                y, x = row.cap + dy - row.oy, row.x0 + dx - row.ox
                canvas = np.zeros_like(row.ink)
                ph = min(p.shape[0], canvas.shape[0] - y)
                pw = min(p.shape[1], canvas.shape[1] - x)
                if y < 0 or x < 0 or ph <= 0 or pw <= 0:
                    continue
                canvas[y : y + ph, x : x + pw] = p[:ph, :pw]
                best = max(best, _ncc(canvas, row.ink))
    return SCALE * (best - 1)


def _assign(S: np.ndarray) -> tuple[float, dict[int, int]]:
    """Best total; rows / names may stay unmatched."""
    nr, nn = S.shape
    big = np.zeros((nr + nn, nn + nr), dtype=float)
    big[:nr, :nn] = np.where(S >= MIN_SCORE, S, -1e6)
    big[:nr, nn:] = ROW_UNMATCHED
    ri, ci = linear_sum_assignment(-big)
    total = float(big[ri, ci].sum())
    return total, {r: c for r, c in zip(ri, ci) if r < nr and c < nn and big[r, c] > -1e5}


def match(
    rows: list[SoftRow], known: Sequence[str], fixed: dict[str, str] | None = None
) -> dict[str, str]:
    """{name: team} for names whose team is clear. fixed: known teams."""
    names = list(known)
    if not rows or not names:
        return {}
    fixed = fixed or {}

    S = np.array([[score(r, n) for n in names] for r in rows])
    return {n: rows[i].team for n, i in decide(rows, names, S, fixed).items()}


def decide(
    rows: list[SoftRow],
    names: list[str],
    S: np.ndarray,
    fixed: dict[str, str] | None = None,
) -> dict[str, int]:
    """{name: row index} for names whose team is clear, from scores S."""
    S = S.copy()
    for j, n in enumerate(names):
        if fixed and n in fixed:  # a known team: only rows of that team, bonus
            for i, r in enumerate(rows):
                S[i, j] = S[i, j] + 5 if r.team == fixed[n] else -1e6
    total, a = _assign(S)

    out = {}
    for i, j in a.items():
        team = rows[i].team
        # Best solution where this name is not in this team.
        S2 = S.copy()
        for k, r in enumerate(rows):
            if r.team == team:
                S2[k, j] = -1e6
        alt, _ = _assign(S2)
        if total - alt >= MARGIN:
            out[names[j]] = i
    return out


def deduce(teams: dict[str, str], roster: Sequence[str]) -> dict[str, str]:
    """Fill teams from game rules. roster: all players of the game."""
    teams = dict(teams)
    # Full roster: 8 teams of n or 4 teams of n. Last open slots.
    counts: dict[str, int] = {}
    for p, t in teams.items():
        if p in roster:
            counts[t] = counts.get(t, 0) + 1
    size = max(counts.values(), default=0)
    if size == 0:
        return teams
    for team_list in (EIGHT_TEAMS, FOUR_TEAMS):
        if len(roster) == len(team_list) * size and set(counts) <= set(team_list):
            break
    else:
        return teams
    unknown = [p for p in roster if p not in teams]
    open_teams = [t for t in team_list if counts.get(t, 0) < size]
    if unknown and len(open_teams) == 1:
        for p in unknown:
            teams[p] = open_teams[0]
    return teams


def read_teams(
    rgb: np.ndarray,
    known: Sequence[str],
    fixed: dict[str, str] | None = None,
) -> dict[str, str]:
    return match(find_rows(rgb), known, fixed)
