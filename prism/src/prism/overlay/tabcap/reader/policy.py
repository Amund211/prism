"""Policy B4: model row reads -> (name, team) list, with no known names.

Port of lab tl_sweep.policy_b(gate_health=True).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from prism.overlay.tabcap.reader.decode import KIND_TOKEN, TEAM_TOKEN
from prism.overlay.tabcap.reader.front import clean, valid
from prism.overlay.tabcap.screenshot import Team

GATE = 3  # rows with token + valid name + health, else no tab list
MAX_HEALTH = 40
NPC_RE = re.compile(r"^[a-z0-9]{8,10}$")
HEALTH_RE = re.compile(r"^[0-9]+$")


@dataclass(frozen=True, slots=True)
class RowRead:
    text: str  # model read of the whole row
    col: int  # tab column
    y: int  # row top


def split_row(text: str) -> tuple[Team | None, str]:
    """Row read -> (team of the token, name): "① [RANK] name 20" -> ("red",
    "name"). The token counts only as the first word; a kind token gives no
    team."""
    words = text.strip().split(" ")
    team = None
    if words and words[0] in TEAM_TOKEN:
        team, words = TEAM_TOKEN[words[0]], words[1:]
    words = [w for w in words if w not in TEAM_TOKEN and w not in KIND_TOKEN]
    if len(words) > 1 and words[-1].isdigit():  # health
        words = words[:-1]
    return team, clean(" ".join(words))


def has_health(text: str) -> bool:
    words = text.strip().split(" ")
    # Not str.isdigit: it is true for the tokens, and int() fails on them
    return (
        len(words) > 1
        and HEALTH_RE.match(words[-1]) is not None
        and int(words[-1]) <= MAX_HEALTH
    )


def policy_b4(rows: Sequence[RowRead]) -> list[tuple[str, Team | None]]:
    """(name, team) per valid name, first read wins; [] if the gate fails"""
    split = [(r, *split_row(r.text)) for r in rows]
    gate = sum(1 for r, t, n in split if t and valid(n) and has_health(r.text))
    if gate < GATE:
        return []
    # Rows sort by team: rows with no token above all team rows are NPCs
    top: dict[int, int] = {}
    for r, t, _ in split:
        if t:
            top[r.col] = min(top.get(r.col, 1 << 30), r.y)
    out: dict[str, Team | None] = {}
    for r, team, n in split:
        if team is None and r.y < top.get(r.col, 0) and NPC_RE.match(n):
            continue
        if valid(n):
            out.setdefault(n, team)
    return list(out.items())
