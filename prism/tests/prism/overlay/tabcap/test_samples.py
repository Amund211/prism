"""
Team recognition on the labeled bucket fixtures (tests/tabcap_fixtures.py).

Off by default (download + minutes of CPU). Run one of:
    uv run pytest tests/prism/overlay/tabcap/test_samples.py --tabcap=train
    ... --tabcap=test
    ... --tabcap=all

Train / test split (prototype plan, "Training and test data"):
- train: one test per train image, asserts the exact outcome in
  tests/data/tabcap_expected.json, plus the summary scores. Algorithm work
  looks at these only.
- test: the summary scores only, no per-image results. Do not tune on them.
- all: per-image tests on train, summary on all fixtures. For the final check.
--tabcap=train --tabcap-update rewrites tabcap_expected.json.

tabcap_expected.json, per image, players by outcome (label = the truth):
- correct: {name: team}
- wrong: {name: "got <team>, label <team>"}
- unknown: {name: "label <team>"} (no team read)
- unscored: {name: team read or null} (no team in the label: respawning,
  spectator, npc, or covered by the overlay)
- extra: {name: team} (known, not in the list, but got a team)
An improvement moves names from wrong / unknown to correct.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests.tabcap_fixtures import (
    DATA_DIR,
    REPORT_KEY,
    Fixture,
    Selection,
    ensure,
    load_manifest,
)

MANIFEST = load_manifest()
EXPECTED = DATA_DIR / "tabcap_expected.json"
TRAIN = [f.name for f in MANIFEST.select("train")]

Outcome = dict[str, dict[str, str | None]]

_results: dict[str, tuple[dict[str, Any], Outcome]] = {}


def outcome(label: dict[str, Any], got: dict[str, str]) -> Outcome:
    out: Outcome = {k: {} for k in ("correct", "wrong", "unknown", "unscored")}
    for row in label["rows"]:
        name, team = row["name"], row["team"]
        if name is None:
            continue
        read = got.get(name)
        if row.get("npc") or row.get("covered") or team is None:
            out["unscored"][name] = read
        elif read == team:
            out["correct"][name] = team
        elif read is None:
            out["unknown"][name] = f"label {team}"
        else:
            out["wrong"][name] = f"got {read}, label {team}"
    names = {row["name"] for row in label["rows"]}
    out["extra"] = {n: t for n, t in got.items() if n not in names}
    return {k: dict(sorted(v.items())) for k, v in out.items()}


def _selection(config: pytest.Config) -> Selection | None:
    selection: Selection | None = config.getoption("tabcap")
    return selection


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "fixture_name" in metafunc.fixturenames:
        per_image = _selection(metafunc.config) in ("train", "all")
        metafunc.parametrize("fixture_name", TRAIN if per_image else [])


@pytest.fixture(scope="module")
def tabcap_dir(request: pytest.FixtureRequest) -> Iterator[Path]:
    selection = _selection(request.config)
    if selection is None:
        pytest.skip("pass --tabcap=train|test|all")
    yield ensure(MANIFEST, MANIFEST.select(selection))

    if request.config.getoption("tabcap_update") and selection == "train":
        # Rewrite all of it: names that left the train split go away
        new = {n: _results[n][1] for n in TRAIN if n in _results}
        if len(new) == len(TRAIN):
            EXPECTED.write_text(json.dumps(new, indent=1, ensure_ascii=False) + "\n")


def _run(name: str, directory: Path) -> tuple[dict[str, Any], Outcome]:
    if name not in _results:
        from PIL import Image

        from prism.overlay.tabcap.teams import read_teams

        label: dict[str, Any] = json.loads((directory / f"{name}.json").read_text())
        with Image.open(directory / f"{name}.png") as image:
            got = read_teams(image, label["known"])
        _results[name] = (label, outcome(label, dict(got)))
    return _results[name]


def test_expected_is_train_split() -> None:
    """tabcap_expected.json has exactly the train images. Needs no download"""
    expected = json.loads(EXPECTED.read_text())
    assert list(expected) == TRAIN, "run --tabcap=train --tabcap-update"


def test_outcome() -> None:
    label = {
        "rows": [
            {"name": "Alice", "team": "red"},
            {"name": "Carol", "team": "green"},
            {"name": "Dave", "team": "gray"},
            {"name": "Eve", "team": None, "state": "respawning"},
            {"name": None, "team": None, "npc": True},
        ]
    }
    got = {"Alice": "red", "Carol": "blue", "Eve": "red", "Frank": "pink"}
    assert outcome(label, got) == {
        "correct": {"Alice": "red"},
        "wrong": {"Carol": "got blue, label green"},
        "unknown": {"Dave": "label gray"},
        "unscored": {"Eve": "red"},
        "extra": {"Frank": "pink"},
    }


def test_fixture(
    fixture_name: str, tabcap_dir: Path, request: pytest.FixtureRequest
) -> None:  # pragma: nocover
    _, result = _run(fixture_name, tabcap_dir)
    if request.config.getoption("tabcap_update"):
        return
    expected = json.loads(EXPECTED.read_text()).get(fixture_name)
    assert result == expected


@dataclass
class Score:
    images: int = 0
    correct: int = 0
    wrong: int = 0
    unknown: int = 0
    extra: int = 0

    def add(self, result: Outcome) -> None:
        self.images += 1
        self.correct += len(result["correct"])
        self.wrong += len(result["wrong"])
        self.unknown += len(result["unknown"])
        self.extra += len(result["extra"])

    def line(self, group: str) -> str:
        rows = self.correct + self.wrong + self.unknown

        def pct(n: int) -> str:
            return f"{n / rows:6.1%}" if rows else "     -"

        return (
            f"{group:<34} {self.images:>4} {rows:>5} {pct(self.correct)} "
            f"{pct(self.wrong)} {pct(self.unknown)} {self.extra:>5}"
        )


def _groups(fixture: Fixture, label: dict[str, Any]) -> list[str]:
    groups = ["all", f"split {fixture.split}", f"source {label['source']}"]
    if fixture.novel:
        groups.append(f"novel: {fixture.novel}")
    return groups


def test_summary(
    tabcap_dir: Path, request: pytest.FixtureRequest
) -> None:  # pragma: nocover
    """Scores per group. Only a report: the per-image tests lock behavior"""
    selection = _selection(request.config)
    assert selection is not None
    scores: dict[str, Score] = {}
    for fixture in MANIFEST.select(selection):
        label, result = _run(fixture.name, tabcap_dir)
        for group in _groups(fixture, label):
            scores.setdefault(group, Score()).add(result)

    header = f"{'group':<34} {'img':>4} {'rows':>5} correct  wrong unknown extra"
    request.config.stash[REPORT_KEY] = [
        f"--tabcap={selection}, {MANIFEST.version}",
        header,
        *(scores[g].line(g) for g in sorted(scores, key=lambda g: (g != "all", g))),
        "Exit criteria: correct >= 85 %, wrong < 2 % (extra counts as wrong)",
    ]
