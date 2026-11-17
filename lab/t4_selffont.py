"""T4: open-set CRNN read, then a self-learned font from the same image:
glyph templates from confident reads; each unsure char is re-chosen among
the CRNN top-k and lookalikes by glyph shape; reads whose glyphs do not fit
their chars are dropped. Font-agnostic (no bank).

TL_MODEL: full (default) or loo (leave own font out). T4_FIX / T4_VERIFY 0: off.
"""

import os

import numpy as np

from d_core import H, glyph_dist, pad, to_font_px
from g_match import regions_of
from i4_rec import logits
from i4_synth import CHARS, norm_crop
from rowparse import LETTER
from rows import runs_of
from tl_front import front, valid

MODEL = os.environ.get("TL_MODEL", "full")
FIX = os.environ.get("T4_FIX", "1") == "1"
VERIFY = os.environ.get("T4_VERIFY", "1") == "1"
SURE, LEARN = 0.9, 0.97
MAX_D = float(os.environ.get("T4_MAX_D", "0.4"))
BY_LETTER = {v: k for k, v in LETTER.items()}
LOOK = [set("O0DoQ"), set("Il1i|!j"), set("S5s$"), set("B8"), set("G6"), set("Z2z"),
        set("A4"), set("Cc"), set("Vv"), set("Ww"), set("Xx"), set("Kk"), set("Uu"),
        set("Pp"), set("gq9y"), set("ae"), set("nmr"), set("hb"), set("t+f")]


def ctc_chars(lp: np.ndarray):
    """[(char, prob, top3 chars)] by greedy CTC"""
    best = lp.argmax(0)
    p = np.exp(lp)
    out = []
    prev = -1
    for t, b in enumerate(best):
        if b > 0 and b != prev:
            out.append([t, b])
        elif b > 0 and b == prev and p[b, t] > p[b, out[-1][0]]:
            out[-1][0] = t
        prev = b
    res = []
    for t, b in out:
        top = [int(i) for i in np.argsort(-p[:, t])[:4] if i > 0]
        res.append((CHARS[b - 1], float(p[b, t]), [CHARS[i - 1] for i in top]))
    return res


def glyphs_of(mask: np.ndarray, k: int) -> list[np.ndarray]:
    return [to_font_px(mask[:, a:b], k) for a, b in runs_of(mask.any(axis=0))]


def strip(chars, team, has_letter):
    """Drop [RANK], a 1-char letter word and words after the name"""
    s = "".join(c for c, _, _ in chars)
    words, cur = [], []
    for i, ch in enumerate(chars):
        if ch[0] == " ":
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(ch)
    if cur:
        words.append(cur)
    words = [w for w in words if not (w[0][0] == "[" or w[-1][0] == "]")]
    if len(words) >= 2 and len(words[0]) == 1:
        words = words[1:]
    if not words:
        return [], s
    w = words[0]
    if not has_letter and len(w) > 16 and w[0][0] in BY_LETTER:
        w = w[1:]
    return w, s


def read_tab(rgb: np.ndarray) -> list[tuple[str, str | None]]:
    _, tab, prows = front(rgb)
    if tab is None or sum(1 for p in prows if p.team) < 3:
        return []
    k = tab.k
    regions = regions_of(rgb, prows, k)
    model = MODEL
    if model == "loo":
        from i4_rec import loo_model

        model = loo_model(rgb, tab, prows, [])
    lps = logits([norm_crop(rgb, r.prow.row.y, r.x0, r.x1, k) for r in regions], model)
    rowlps = logits([norm_crop(rgb, r.prow.row.y, r.prow.row.x0, r.prow.row.x1, k) for r in regions], model)
    items = []
    for r, lp, rlp in zip(regions, lps, rowlps):
        chars, _ = strip(ctc_chars(lp), r.prow.team, r.prow.letter is not None)
        row = "".join(c for c, _, _ in ctc_chars(rlp)).replace(" ", "")
        g = glyphs_of(r.mask, k)
        items.append({"r": r, "chars": chars, "glyphs": g if len(g) == len(chars) else None, "row": row})
    # learn the image's font from sure reads
    samples: dict[str, list[np.ndarray]] = {}
    for it in items:
        if it["glyphs"] is None or not it["chars"]:
            continue
        if min(p for _, p, _ in it["chars"]) < LEARN:
            continue
        for (c, _, _), gl in zip(it["chars"], it["glyphs"]):
            samples.setdefault(c, []).append(pad(gl))
    T = {c: np.stack(v[:6]) for c, v in samples.items()}

    def dist(gl: np.ndarray, c: str) -> float | None:
        if c not in T:
            return None
        return float(glyph_dist(pad(gl)[None], T[c]).min())

    out: dict[str, str | None] = {}
    for it in items:
        chars = list(it["chars"])
        if not chars:
            continue
        text = [c for c, _, _ in chars]
        bad = False
        if it["glyphs"] is not None and T:
            for i, ((c, p, top), gl) in enumerate(zip(chars, it["glyphs"])):
                if FIX and p < SURE:
                    cand = set(top) | set().union(*(s for s in LOOK if c in s))
                    scored = [(dist(gl, x), x) for x in cand if dist(gl, x) is not None]
                    if scored:
                        d, x = min(scored)
                        d0 = dist(gl, c)
                        if x != c and d < 0.3 and (d0 is None or d0 - d >= 0.1):
                            text[i] = x
                if VERIFY:
                    d = dist(gl, text[i])
                    if d is not None and d > MAX_D:
                        bad = True
        n = "".join(text)
        if bad or not valid(n):
            continue
        team = it["r"].prow.team
        if team is None and n in it["row"]:
            pre = it["row"][: it["row"].index(n)]
            if len(pre) == 1 and pre in BY_LETTER:
                team = BY_LETTER[pre]
        out.setdefault(n, team)
    return list(out.items())
