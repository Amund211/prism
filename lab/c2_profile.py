"""C2: column ink profiles (3 bands), each word and each vanilla name
resampled to a fixed length (uniform stretch = font width scale), L1
distance after a small blur. Fully vectorised."""

import numpy as np

from c_feats import RowF, assign_loo, feats, name_profile

L = 48
ACCEPT = (0.20, 0.08)
W_WIDTH = 0.5


def resample(p: np.ndarray) -> np.ndarray:
    """3 x w -> 3 x L, ink normalised per band set"""
    w = p.shape[1]
    if w == 0:
        return np.zeros((3, L), np.float32)
    x = (np.arange(L) + 0.5) * w / L - 0.5
    out = np.stack([np.interp(x, np.arange(w), b) for b in p])
    # blur 1 bin: tolerance for small shifts
    out = (np.roll(out, 1, axis=1) + 2 * out + np.roll(out, -1, axis=1)) / 4
    return out / max(out.sum(), 1e-6)


def costs(rows: list[RowF], known: list[str]) -> np.ndarray:
    R = np.stack([resample(r.profile) for r in rows]).reshape(len(rows), -1)
    N = np.stack([resample(name_profile(n)) for n in known]).reshape(len(known), -1)
    d = np.abs(R[:, None, :] - N[None, :, :]).sum(axis=2) / 2  # 0..1
    rw = np.log(np.maximum([r.width for r in rows], 1))
    nw = np.log(np.maximum([name_profile(n).shape[1] for n in known], 1))
    lr = rw[:, None] - nw[None, :]
    s = np.median(lr[np.arange(len(rows)), np.abs(lr).argmin(axis=1)])
    wc = np.minimum(np.abs(lr - s) * 4, 1.5)
    return (d + W_WIDTH * wc) / (1 + W_WIDTH)


def match(rows: list[RowF], known: list[str], max_cost: float = ACCEPT[0], margin: float = ACCEPT[1]) -> dict[str, str]:
    if not rows or not known:
        return {}
    pairs = assign_loo(costs(rows, known), max_cost, margin)
    return {known[j]: rows[i].team for i, j in pairs if rows[i].team}


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return match(feats(rgb), known)
