"""Charset of the model and greedy CTC decode.

The charset order must match the training order (lab c2_synth.CHARS_K):
the model emits index i + 1 for CHARS_K[i], and 0 for the CTC blank.
"""

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
