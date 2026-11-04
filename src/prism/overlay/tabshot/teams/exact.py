"""
Algorithm A: read teams from exact (unscaled, unblurred) tab-list pixels.

No font, OCR or game settings. Steps:
1. Text pixels: pixels in a team color pattern (any shade, for pack fonts)
   with a drop shadow (pixel / 4) one GUI px down-right. The offset with
   the most shadows is the GUI scale.
2. Components -> words (same color, same baseline, small gaps) -> glyphs.
3. Row = one-glyph team letter (bold) + space + name word, same color.
4. Match rows to known names as a substitution cipher: one glyph image is
   one character everywhere in the image. Keep only matches that are the
   same in every best solution and that have enough evidence.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy import ndimage  # type: ignore[import-untyped]

from prism.overlay.tabshot.screenshot import Team

TEAMS: dict[Team, tuple[int, str]] = {
    # team: (rgb, letter)
    "aqua": (0x55FFFF, "A"),
    "blue": (0x5555FF, "B"),
    "green": (0x55FF55, "G"),
    "pink": (0xFF55FF, "P"),
    "red": (0xFF5555, "R"),
    "white": (0xFFFFFF, "W"),
    "gray": (0x555555, "S"),
    "yellow": (0xFFFF55, "Y"),
}
TEAM_NAMES: list[Team] = list(TEAMS)
GRAY = TEAM_NAMES.index("gray")
WHITE = TEAM_NAMES.index("white")
# 1 = high channel, 0 = a third of high (0x55 vs 0xFF)
PATTERNS = [
    tuple(int(((c >> sh) & 0xFF) == 0xFF) for sh in (16, 8, 0))
    for c, _ in TEAMS.values()
]
MIN_SHADE = 0.7  # Darker edge pixels of pack fonts make glyphs touch
MAX_SCALE = 6
MAX_NODES = 50_000
MIN_EVIDENCE = 0.25

IntArray = npt.NDArray[Any]


@dataclass
class Comp:
    color: int
    y0: int
    y1: int
    x0: int
    x1: int  # Exclusive
    label: int


@dataclass
class Glyph:
    x0: int
    x1: int
    gid: int


@dataclass
class Word:
    color: int
    comps: list[Comp]
    base: int  # Baseline: lowest bottom of chained comps (no dots)
    glyphs: list[Glyph] = field(default_factory=list)

    @property
    def x0(self) -> int:
        return min(c.x0 for c in self.comps)

    @property
    def x1(self) -> int:
        return max(c.x1 for c in self.comps)

    @property
    def y0(self) -> int:
        return min(c.y0 for c in self.comps)

    @property
    def y1(self) -> int:
        return max(c.y1 for c in self.comps)


@dataclass
class Row:
    team: Team
    letter: int  # gid
    name: tuple[int, ...]  # gids
    box: tuple[int, int, int, int]  # x0, y0, x1, y1


def classify(a: IntArray, hi: IntArray) -> IntArray:
    """Team index per pixel by color pattern, -1 = none. a: int16 HxWx3"""
    cls = np.full(hi.shape, -1, dtype=np.int8)
    ok_hi = [np.abs(a[..., ch] - hi) <= 3 for ch in range(3)]
    ok_lo = [np.abs(3 * a[..., ch] - hi) <= 9 for ch in range(3)]
    bright = hi >= MIN_SHADE * 255
    for i, pat in enumerate(PATTERNS):
        if i == GRAY:
            continue
        m = bright.copy()
        for ch, high in enumerate(pat):
            m &= ok_hi[ch] if high else ok_lo[ch]
        cls[m] = i
    m = (hi >= MIN_SHADE * 0x55) & (hi <= 0x55) & ok_hi[0] & ok_hi[1] & ok_hi[2]
    cls[m] = GRAY
    return cls


def find_text(rgb: IntArray) -> tuple[IntArray, int]:
    """Team index per text pixel (-1 = not text), and GUI scale"""
    a = rgb.astype(np.int16)
    h, w = a.shape[:2]
    hi = a.max(axis=2)
    cls = classify(a, hi)
    cand = cls >= 0

    def shadows(s: int) -> IntArray:
        """Mask: candidate pixel whose (+s, +s) pixel is about pixel / 4"""
        out = np.zeros((h, w), dtype=bool)
        # Cheap test on the max channel first, then all channels
        m = cand[:-s, :-s] & (np.abs(hi[s:, s:] - (hi[:-s, :-s] >> 2)) <= 2)
        ys, xs = np.nonzero(m)
        diff = np.abs(a[ys + s, xs + s] - (a[ys, xs] >> 2))
        ok = (diff <= 2).all(axis=1)
        out[ys[ok], xs[ok]] = True
        return out

    hits = [int(shadows(s).sum()) for s in range(1, MAX_SCALE + 1)]
    s = 1 + int(np.argmax(hits))

    # Text = candidate whose (+s, +s) pixel is its shadow, or is text of the
    # same color (inner glyph pixels)
    text = shadows(s)
    same = np.zeros((h, w), dtype=bool)
    same[:-s, :-s] = cand[:-s, :-s] & (cls[:-s, :-s] == cls[s:, s:])
    # Gray / white text on stone / snow: background pixels fit the class
    # too, so ask for the exact same color there
    packed = (a[..., 0].astype(np.int32) << 16) | (a[..., 1] << 8) | a[..., 2]
    neutral = (cls[:-s, :-s] == GRAY) | (cls[:-s, :-s] == WHITE)
    same[:-s, :-s] &= ~neutral | (packed[:-s, :-s] == packed[s:, s:])
    for _ in range(12):
        nxt = text.copy()
        nxt[:-s, :-s] |= same[:-s, :-s] & text[s:, s:]
        if (nxt == text).all():
            break
        text = nxt
    return np.where(text, cls, -1).astype(np.int8), s


def find_comps(idx: IntArray, s: int) -> tuple[IntArray, list[Comp]]:
    labels, _ = ndimage.label(idx >= 0, structure=np.ones((3, 3)))
    comps = []
    for i, sl in enumerate(ndimage.find_objects(labels)):
        ys, xs = sl
        if ys.stop - ys.start > 12 * s or xs.stop - xs.start > 12 * s:
            continue
        color = int(idx[ys.start, xs][labels[ys.start, xs] == i + 1][0])
        comps.append(Comp(color, ys.start, ys.stop, xs.start, xs.stop, i + 1))
    return labels, comps


def find_words(labels: IntArray, comps: list[Comp], s: int) -> list[Word]:
    words: list[Word] = []
    open_words: dict[int, list[Word]] = {}
    for c in sorted(comps, key=lambda c: c.x0):
        cands = [w for w in open_words.get(c.color, []) if w.x1 >= c.x0 - 3 * s]
        open_words[c.color] = cands
        # Same baseline; descenders and '_' go up to 3 GUI px lower. The
        # next row is 9 GUI px lower.
        fits = [w for w in cands if w.x1 <= c.x0 and abs(c.y1 - w.base) <= 3 * s]
        if fits:
            w = min(fits, key=lambda w: abs(c.y1 - w.base))
            w.comps.append(c)
            w.base = min(w.base, c.y1)
        else:
            w = Word(c.color, [c], c.y1)
            words.append(w)
            cands.append(w)

    # Dots of 'i' / 'j' are not on the baseline: attach them to the word
    # under them
    dots = [w for w in words if len(w.comps) == 1 and w.y1 - w.y0 <= 2 * s]
    for d in dots:
        dc = d.comps[0]
        for w in words:
            if (
                w is not d
                and w.comps
                and w.color == d.color
                and w.y0 - 3 * s <= dc.y0
                and dc.y1 <= w.base - s
                and any(c.x0 < dc.x1 and dc.x0 < c.x1 for c in w.comps)
            ):
                w.comps.append(dc)
                d.comps = []
                break
    words = [w for w in words if w.comps]

    # Glyphs: comps with overlapping columns
    shapes: dict[tuple[int, tuple[int, ...], bytes], int] = {}
    for w in words:
        groups: list[list[Comp]] = []
        for c in sorted(w.comps, key=lambda c: c.x0):
            if groups and c.x0 < max(g.x1 for g in groups[-1]):
                groups[-1].append(c)
            else:
                groups.append([c])
        for g in groups:
            x0, x1 = min(c.x0 for c in g), max(c.x1 for c in g)
            y0, y1 = min(c.y0 for c in g), max(c.y1 for c in g)
            mask = np.isin(labels[y0:y1, x0:x1], [c.label for c in g])
            # Position relative to the baseline tells 'o' from 'O' etc.
            key = (y1 - w.base, mask.shape, np.packbits(mask).tobytes())
            w.glyphs.append(Glyph(x0, x1, shapes.setdefault(key, len(shapes))))
    return words


def find_rows(words: list[Word], s: int) -> list[Row]:
    singles = [w for w in words if len(w.glyphs) == 1]
    rows = []
    for n in words:
        if not 3 <= len(n.glyphs) <= 16:
            continue
        for letter in singles:
            if (
                letter.color == n.color
                and 3 * s <= n.x0 - letter.x1 <= 9 * s
                and abs(letter.base - n.base) <= s
            ):
                rows.append(
                    Row(
                        team=TEAM_NAMES[n.color],
                        letter=letter.glyphs[0].gid,
                        name=tuple(g.gid for g in n.glyphs),
                        box=(letter.x0, n.y0, n.x1, n.y1),
                    )
                )
                break
    # The tab list uses one letter glyph per team; drop rows (chat, HUD)
    # with another one, if one letter glyph is clearly the most common
    drop = set()
    for team in {r.team for r in rows}:
        letters = [r.letter for r in rows if r.team == team]
        counts = sorted((letters.count(g), g) for g in set(letters))
        if len(counts) > 1 and counts[-1][0] > counts[-2][0]:
            drop |= {(team, g) for _, g in counts[:-1]}
    return [r for r in rows if (r.team, r.letter) not in drop]


def _pairs(row: Row, name: str) -> list[tuple[str, int]] | None:
    """(char, gid) pairs if row can be name on its own, else None"""
    if len(name) != len(row.name):
        return None
    # The team letter is bold: its own namespace, not the name glyphs
    pairs = [("bold:" + TEAMS[row.team][1], row.letter), *zip(name, row.name)]
    c2g: dict[str, int] = {}
    g2c: dict[int, str] = {}
    for c, g in pairs:
        if c2g.setdefault(c, g) != g or g2c.setdefault(g, c) != c:
            return None
    return pairs


def match(rows: list[Row], known: Iterable[str]) -> dict[int, str]:
    """Row index -> name, for rows with one answer in all best solutions"""
    seen = solve(rows, known)
    if seen is None:
        return {}
    out: dict[int, str] = {}
    for i, st in enumerate(seen):
        if len(st) == 1 and (name := next(iter(st))) is not None:
            out[i] = name
    # Evidence: a glyph is confirmed if it shows up twice among the matched
    # names. If most glyphs of a name are seen only once, any name of the
    # same length would fit (blur, unknown font): do not trust it.
    counts: dict[int, int] = {}
    for i in out:
        for g in rows[i].name:
            counts[g] = counts.get(g, 0) + 1
    return {
        i: n
        for i, n in out.items()
        if sum(counts[g] > 1 for g in rows[i].name) >= MIN_EVIDENCE * len(n)
    }


def solve(rows: list[Row], known: Iterable[str]) -> list[set[str | None]] | None:
    """
    Per row: the names it gets in the best solutions (None = no name).

    Best = most rows matched, with one consistent glyph <-> char map.
    """
    names = sorted(set(known))
    cands = [
        [(name, p) for name in names if (p := _pairs(r, name)) is not None]
        for r in rows
    ]
    order = sorted(range(len(rows)), key=lambda i: len(cands[i]))
    best = -1
    seen: list[set[str | None]] = [set() for _ in rows]
    nodes = 0
    assign: dict[int, str | None] = {}
    c2g: dict[str, int] = {}
    g2c: dict[int, str] = {}
    used: set[str] = set()

    def dfs(k: int, count: int) -> None:
        nonlocal best, nodes
        nodes += 1
        if nodes > MAX_NODES or count + (len(order) - k) < best:
            return
        if k == len(order):
            if count > best:
                best = count
                for st in seen:
                    st.clear()
            for i, v in assign.items():
                seen[i].add(v)
            return
        i = order[k]
        for name, pairs in cands[i]:
            if name in used:
                continue
            added = []
            ok = True
            for c, g in pairs:
                cg, gc = c2g.get(c), g2c.get(g)
                if cg is None and gc is None:
                    c2g[c], g2c[g] = g, c
                    added.append((c, g))
                elif cg != g or gc != c:
                    ok = False
                    break
            if ok:
                used.add(name)
                assign[i] = name
                dfs(k + 1, count + 1)
                used.discard(name)
            for c, g in added:
                del c2g[c], g2c[g]
        assign[i] = None
        dfs(k + 1, count)
        del assign[i]

    dfs(0, 0)
    return None if nodes > MAX_NODES else seen


def read_teams(rgb: IntArray, known: Sequence[str]) -> dict[str, Team]:
    """{name: team} for the known names we could read. rgb: HxWx3 uint8"""
    idx, s = find_text(rgb)
    labels, comps = find_comps(idx, s)
    rows = find_rows(find_words(labels, comps, s), s)
    return {name: rows[i].team for i, name in match(rows, known).items()}
