"""Tab rows -> parsed rows (words, name, team letter)."""

from dataclasses import dataclass

import numpy as np

from prism.overlay.tabcap.reader.front.guiscale import Array
from prism.overlay.tabcap.reader.front.rowparse import (
    RowText,
    Word,
    gaps,
    nearest_team,
    row_text,
    words,
)
from prism.overlay.tabcap.reader.front.rows import Row, Tab, find_tab, runs_of


@dataclass
class PRow:
    row: Row
    letter: Word | None
    name: Word | None
    team: str | None  # from the letter colour; None if no letter
    words: list[Word]


def parse(rgb: Array, tab: Tab | None = None) -> tuple[Tab | None, list[PRow]]:
    tab = tab or find_tab(rgb)
    if tab is None:
        return None, []
    out = []
    k = tab.k
    rts = [row_text(rgb, tab.mask, r) for r in tab.rows]
    gap = word_gap([rt for rt in rts if rt], k)
    for r, rt in zip(tab.rows, rts):
        ws = words(rgb, tab.mask, r, gap=gap, rt=rt) if rt else []
        if not ws:
            continue
        # names have >= 3 chars; head icons can give 1-2 spans
        name = next((w for w in ws if len(w.spans) >= 3 and w.x1 - w.x0 >= 9 * k), None)
        letter = find_letter(rgb, r, name, reach=7 + 2 * gap) if name else None
        team = team_of(name) if letter and name else None
        out.append(PRow(r, letter, name, team, ws))
    # The letter-to-name gap is the same in all rows (one font, one space).
    # A client icon before a letterless name (Lunar) has another gap.
    lg = [p.name.x0 - p.letter.x1 for p in out if p.letter and p.name]
    if len(lg) >= 3:
        med = float(np.median(lg))
        for p in out:
            if p.letter and p.name and abs(p.name.x0 - p.letter.x1 - med) > 2.5 * k:
                p.letter, p.team = None, None
    return tab, out


def word_gap(rts: list[RowText], k: int) -> float:
    """Word-split gap in units of k: fonts with wide letter spacing need more
    than the default 2.5. The most common gap is the gap between glyphs."""
    g = [x for rt in rts for x in gaps(rt) if x > 0]
    if len(g) < 10:
        return 2.5
    vals, counts = np.unique(g, return_counts=True)
    g0 = vals[counts.argmax()]
    return float(max(2.5, 1.7 * g0 / k))


def team_of(w: Word) -> str | None:
    """Palette team of the text colour; else of the shadow x4 (packs that
    remap text colours keep the vanilla shadow)"""
    t = nearest_team(w.color)
    if t is None:
        t = nearest_team(tuple(min(255, 4 * c + 2) for c in w.shadow), max_dist=50)
    return t


def shade_of(px: Array, color: tuple[int, ...], lo: float = 0.55) -> Array:
    """Pixels that are the colour, or a darker shade of it (shaded fonts)"""
    c = np.array(color, np.float32)
    strong = c >= 40  # ratios of near-zero channels are noise
    p = px.astype(np.float32)
    ratio = p[..., strong] / c[strong]
    hi_, lo_ = ratio.max(axis=-1), ratio.min(axis=-1)
    ok = (hi_ - lo_ <= 0.12) & (lo_ >= lo) & (hi_ <= 1.05)
    if not strong.all():
        ok &= (p[..., ~strong] <= 48).all(axis=-1)
    return ok


def find_letter(rgb: Array, r: Row, name: Word, reach: float = 13) -> Word | None:
    """A glyph in the name colour just left of the name (the team letter),
    within reach * k. Checks colour, not the word split, so client icons
    next to it do not matter."""
    k = r.k
    a = max(0, name.x0 - int(reach * k))
    # >= 3k: a space follows the letter; client icons (Lunar) sit closer
    b = name.x0 - 3 * k
    if b <= a:
        return None
    band = rgb[r.y : r.y + 8 * k, a:b]
    # lo 0.75: shaded fonts stay above it; the dark panel can match a lower
    # bound for dark colours (gray team 85,85,85)
    m = shade_of(band, name.color, lo=0.75)
    spans = runs_of(m.sum(axis=0) >= k)
    if not spans:
        return None
    p, q = spans[-1]
    while len(spans) >= 2 and p - spans[-2][1] < k + 1:  # glyph parts
        spans.pop()
        p = spans[-1][0]
    rows_on = np.flatnonzero(m[:, p:q].any(axis=1))
    if (
        not (2 * k <= q - p <= 8 * k)
        or len(rows_on) == 0
        or rows_on[-1] - rows_on[0] < 5 * k
    ):
        return None
    exact = (
        np.abs(band[:, p:q].astype(np.int16) - np.array(name.color, np.int16)).max(
            axis=2
        )
        <= 12
    )
    if exact.sum() < 2 * k * k:
        return None
    return Word(a + p, a + q, [(a + p, a + q)], name.color, name.shadow, m[:, p:q])
