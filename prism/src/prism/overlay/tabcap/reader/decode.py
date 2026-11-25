"""Charset of the model, greedy CTC decode, and the sequence posterior.

The charset order must match the training order (lab c2_synth.CHARS_K):
the model emits index i + 1 for CHARS_K[i], and 0 for the CTC blank.
"""

import math

import numpy as np

from prism.overlay.tabcap.reader.front.guiscale import Array
from prism.overlay.tabcap.screenshot import Team

CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_[]+ "
# One output symbol per team in place of the team letter
TEAM_TOKEN: dict[str, Team] = {
    "①": "red",
    "②": "blue",
    "③": "green",
    "④": "yellow",
    "⑤": "aqua",
    "⑥": "white",
    "⑦": "pink",
    "⑧": "gray",
}
# Lobby rows with no team letter: respawning = gray name, spectator = white name
KIND_TOKEN = {"⑨": "respawning", "⑩": "spectator"}
CHARS_K = CHARS + "".join(TEAM_TOKEN) + "".join(KIND_TOKEN)


def decode(logits: Array) -> str:
    """C x T logits -> text: best class per step, repeats merged, blanks dropped"""
    best = logits.argmax(0)
    keep = (best != np.concatenate([[-1], best[:-1]])) & (best > 0)
    return "".join(CHARS_K[b - 1] for b in best[keep])


BEAM_WIDTH = 10
BEAM_PRUNE = -7.0  # log prob: chars under it are not tried at a step
NINF = -math.inf


def _lse(a: float, b: float) -> float:
    # math, not numpy: numpy calls on single numbers made the beam 5x slower
    if a == NINF:
        return b
    if b == NINF:
        return a
    m = max(a, b)
    return m + math.log1p(math.exp(-abs(a - b)))


def posterior(logits: Array) -> float:
    """P(best read) among the CTC prefix-beam N-best: how sure the model is
    of the whole row (lab u_decode.beam + posterior)"""
    lp = logits.astype(np.float64)
    lp = lp - np.logaddexp.reduce(lp, axis=0)
    # prefix -> (log p ending in blank, log p ending in a char)
    beams: dict[tuple[int, ...], tuple[float, float]] = {(): (0.0, NINF)}
    for col_np in lp.T:
        col = col_np.tolist()
        cand = [int(c) for c in np.flatnonzero(col_np > BEAM_PRUNE) if c > 0]
        nxt: dict[tuple[int, ...], tuple[float, float]] = {}

        def add(p: tuple[int, ...], b: float, nb: float) -> None:
            ob, onb = nxt.get(p, (NINF, NINF))
            nxt[p] = (_lse(ob, b), _lse(onb, nb))

        for p, (pb, pnb) in beams.items():
            tot = _lse(pb, pnb)
            add(p, tot + col[0], NINF)
            for c in cand:
                if p and p[-1] == c:
                    add(p, NINF, pnb + col[c])  # repeat with no blank: same
                    add(p + (c,), NINF, pb + col[c])
                else:
                    add(p + (c,), NINF, tot + col[c])
        top = sorted(nxt.items(), key=lambda kv: -_lse(*kv[1]))
        beams = dict(top[:BEAM_WIDTH])
    scores = [_lse(*v) for v in beams.values()]
    best = max(scores)
    return 1 / sum(math.exp(s - best) for s in scores)
