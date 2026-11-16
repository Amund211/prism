"""C5: C1q with the alignment DP vectorised over all (row, name) pairs.
Same costs as c1_runs.align (checked by c5_check.py)."""

import numpy as np

import c1v_q
from c1_runs import H_W, MERGE, SKIP, SPLIT, calibrated
from c_feats import RowF, feats


def _pad(seqs: list[list[float]], width: int) -> np.ndarray:
    out = np.zeros((len(seqs), width))
    for i, s in enumerate(seqs):
        out[i, : len(s)] = s
    return out


def costs(rows: list[RowF], known: list[str]) -> np.ndarray:
    model = calibrated(rows, known)
    s = model.s
    R, N = len(rows), len(known)
    nl = np.array([len(r.runs) for r in rows])
    ml = np.array([len(n) for n in known])
    n_, m_ = int(nl.max()), int(ml.max())
    rw = _pad([[g.w for g in r.runs] for r in rows], n_)[:, None, :]  # R,1,n
    rt = _pad([[g.top for g in r.runs] for r in rows], n_)[:, None, :]
    rb = _pad([[g.bot for g in r.runs] for r in rows], n_)[:, None, :]
    gl = [model.name(n) for n in known]
    cw = _pad([[g.w for g in x] for x in gl], m_)[None]  # 1,N,m
    ct = _pad([[g.top for g in x] for x in gl], m_)[None]
    cb = _pad([[g.bot for g in x] for x in gl], m_)[None]

    def gc(w, top, bot, i):  # run i-1 vs (w, top, bot): R,N
        dw = np.minimum(1.5, np.abs(rw[:, :, i] - w) / np.maximum(w, 1.5))
        dh = np.minimum(1.0, np.abs(rt[:, :, i] - top) / 2) + np.minimum(1.0, np.abs(rb[:, :, i] - bot) / 1.5)
        return dw + H_W * dh

    D = np.full((n_ + 1, m_ + 1, R, N), 1e9)
    D[0] = (np.arange(m_ + 1) * SKIP)[:, None, None]
    D[:, 0] = (np.arange(n_ + 1) * SKIP)[:, None, None]
    for i in range(1, n_ + 1):
        for j in range(1, m_ + 1):
            best = np.minimum(D[i - 1, j], D[i, j - 1]) + SKIP
            w = np.full((1, N), -s)
            top = np.full((1, N), 9.0)
            bot = np.full((1, N), -1.0)
            for t in range(1, 4):
                if j - t < 0:
                    break
                w = w + cw[:, :, j - t] + s
                top = np.minimum(top, ct[:, :, j - t])
                bot = np.maximum(bot, cb[:, :, j - t])
                best = np.minimum(best, D[i - 1, j - t] + gc(w, top, bot, i - 1) + MERGE * (t - 1))
            if i >= 2:
                bw = rw[:, :, i - 1] + rw[:, :, i - 2] + s
                bt = np.minimum(rt[:, :, i - 1], rt[:, :, i - 2])
                bb = np.maximum(rb[:, :, i - 1], rb[:, :, i - 2])
                c = cw[:, :, j - 1]
                dw = np.minimum(1.5, np.abs(bw - c) / np.maximum(c, 1.5))
                dh = np.minimum(1.0, np.abs(bt - ct[:, :, j - 1]) / 2) + np.minimum(1.0, np.abs(bb - cb[:, :, j - 1]) / 1.5)
                best = np.minimum(best, D[i - 2, j - 1] + dw + H_W * dh + SPLIT)
            D[i, j] = best
    ri = np.arange(R)[:, None]
    ni = np.arange(N)[None, :]
    final = D[nl[:, None], ml[None, :], ri, ni]
    return final / np.maximum(np.maximum(nl[:, None], ml[None, :]), 1)


def match(rows: list[RowF], known: list[str]) -> dict[str, str]:
    if not rows or not known:
        return {}
    pairs = c1v_q.accept(costs(rows, known), *c1v_q.ACCEPT)
    return {known[j]: rows[i].team for i, j in pairs if rows[i].team}


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return match(feats(rgb), known)
