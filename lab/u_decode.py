"""CTC decode helpers for the u_* experiments: prefix beam search, N-best,
sequence posterior, rescoring over several crops."""

import numpy as np

from i4_rec import ctc_nll
from i4_synth import CHARS


def _lse(a: float, b: float) -> float:
    if a == -np.inf:
        return b
    if b == -np.inf:
        return a
    m = max(a, b)
    return m + np.log1p(np.exp(-abs(a - b)))


def beam(lp: np.ndarray, width: int = 10, prune: float = -7.0) -> list[tuple[str, float]]:
    """CTC prefix beam search on log-probs C x T -> [(text, log p)] best first"""
    lp = lp.astype(np.float64)
    C, T = lp.shape
    beams = {"": (0.0, -np.inf)}  # prefix -> (log p ending in blank, log p ending in char)
    for t in range(T):
        col = lp[:, t]
        cand = [c for c in np.nonzero(col > prune)[0] if c > 0]
        nxt: dict[str, list[float]] = {}

        def add(p, b, nb):
            o = nxt.setdefault(p, [-np.inf, -np.inf])
            o[0], o[1] = _lse(o[0], b), _lse(o[1], nb)

        for p, (pb, pnb) in beams.items():
            tot = _lse(pb, pnb)
            add(p, tot + col[0], -np.inf)
            last = p[-1] if p else None
            for c in cand:
                ch = CHARS[c - 1]
                if ch == last:
                    add(p, -np.inf, pnb + col[c])  # repeat, no blank between
                    add(p + ch, -np.inf, pb + col[c])
                else:
                    add(p + ch, -np.inf, tot + col[c])
        beams = dict(sorted(nxt.items(), key=lambda kv: -_lse(*kv[1]))[:width])
    out = [(p, _lse(*v)) for p, v in beams.items()]
    return sorted(out, key=lambda x: -x[1])


def posterior(nbest: list[tuple[str, float]]) -> float:
    """P(top-1) among the N-best"""
    ls = np.array([s for _, s in nbest])
    return float(np.exp(ls[0] - np.logaddexp.reduce(ls)))


def rescore(cands: list[str], lps: list[np.ndarray]) -> np.ndarray:
    """Summed CTC NLL of each candidate over several crops (lower is better)"""
    cands = [c for c in cands]
    tot = np.zeros(len(cands))
    for lp in lps:
        tot += ctc_nll(lp.astype(np.float64), [c or " " for c in cands])
    return tot
