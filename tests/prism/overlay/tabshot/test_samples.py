"""
Team recognition on the labeled samples (local only, not in git).

Put the samples (PNGs + labels.json) in tests/data/tabshot/, e.g. as a
symlink to the prototype plan's samples/ dir. Skipped if missing.
"""

import json
from pathlib import Path
from typing import Any

import pytest

SAMPLES_DIR = Path(__file__).parents[3] / "data" / "tabshot"
LABELS = SAMPLES_DIR / "labels.json"

pytestmark = pytest.mark.skipif(not LABELS.is_file(), reason="no local samples")


def _players(label: dict[str, Any]) -> set[str]:
    return {r["name"] for r in label["rows"] if not r.get("npc")}


def test_samples() -> None:  # pragma: nocover
    from PIL import Image

    from prism.overlay.tabshot.teams import read_teams

    labels: dict[str, dict[str, Any]] = json.loads(LABELS.read_text())
    ok = wrong = unknown = 0
    notes = []
    for file, label in sorted(labels.items()):
        # Known names: this game's players (dead players are not in the list)
        game = _players(label)
        for other in labels.values():
            if len(_players(other) & game) >= 5:
                game |= _players(other)

        with Image.open(SAMPLES_DIR / file) as image:
            got = read_teams(image, game)

        for row in label["rows"]:
            if row.get("npc") or row["team"] is None or row.get("covered"):
                continue
            team = got.get(row["name"])
            if team == row["team"]:
                ok += 1
            elif team is None:
                unknown += 1
            else:
                wrong += 1
                notes.append(f"{file}: {row['name']} is {row['team']}, got {team}")

    total = ok + wrong + unknown
    print(f"correct {ok / total:.1%} wrong {wrong / total:.1%} of {total}")
    assert notes == []
    # Prototype "AE" at 1080p: 85.2 % (2026-11-04)
    assert ok / total >= 0.85
