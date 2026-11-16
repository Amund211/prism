"""E2d: union of E2 (parser name crops) and E2c (full row bands). A name gets
no team if the two disagree, or if E2c found the name with no glyph before it
(no team letter: spectator / respawning)."""

import numpy as np

import e2_rapidocr
import e2c_rowband

VETO = False  # E2c "no letter" vetoes E2: -11 points correct, so off


def combine(a: dict[str, str], c: dict[str, str | None]) -> dict[str, str]:
    out = dict(a)
    for n, t in c.items():
        if t is None:
            if VETO:
                out.pop(n, None)
        elif t == "?":
            continue
        elif n not in out:
            out[n] = t
        elif out[n] != t:
            del out[n]
    return out


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return combine(e2_rapidocr.read_teams(rgb, known), e2c_rowband.read_all(rgb, known))
