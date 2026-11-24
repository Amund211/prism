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

tabcap_expected.json, per image, players by outcome (label = the truth,
fixtures schema v2: every row scored, see the fixtures README):
- correct: {name: team, or null for a row with no team that got none}
- wrong: {name: "got <team>, label <team or no team>"}
- unknown: {name: "label <team>"} (has a team, none read)
- npc: {name: team} (an NPC row, not a player; an error)
- extra: {name: team} (not in the list: dead or left; an error)
An improvement moves names from wrong / unknown to correct.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
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
WEIGHTS: dict[str, float] = json.loads((DATA_DIR / "tabcap_weights.json").read_text())[
    "weights"
]

Outcome = dict[str, dict[str, str | None]]

_results: dict[str, tuple[dict[str, Any], Outcome]] = {}


def outcome(label: dict[str, Any], got: dict[str, str]) -> Outcome:
    out: Outcome = {k: {} for k in ("correct", "wrong", "unknown")}
    for row in label["rows"]:
        name, team = row["name"], row["team"]
        read = got.get(name)
        if read == team:
            out["correct"][name] = team
        elif read is None:
            out["unknown"][name] = f"label {team}"
        else:
            out["wrong"][name] = f"got {read}, label {team or 'no team'}"
    names = {row["name"] for row in label["rows"]}
    npcs = set(label["npcs"])
    out["npc"] = {n: t for n, t in got.items() if n in npcs}
    out["extra"] = {n: t for n, t in got.items() if n not in names | npcs}
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

        from prism.overlay.tabcap.reader import read_teams

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
            {"name": "Me", "team": None, "state": "spectator", "covered": True},
            {"name": "Zed", "team": "aqua", "covered": True},
        ],
        "npcs": ["tizignbh", None],
    }
    got = {
        "Alice": "red",
        "Carol": "blue",
        "Eve": "red",
        "Zed": "aqua",
        "tizignbh": "pink",
        "Gone": "white",
    }
    assert outcome(label, got) == {
        "correct": {"Alice": "red", "Me": None, "Zed": "aqua"},
        "wrong": {"Carol": "got blue, label green", "Eve": "got red, label no team"},
        "unknown": {"Dave": "label gray"},
        "npc": {"tizignbh": "pink"},
        "extra": {"Gone": "white"},
    }


def test_weights_cover_manifest() -> None:
    """Every fixture has a weight, and only fixtures. Needs no download"""
    assert sorted(WEIGHTS) == sorted(MANIFEST.fixtures)
    assert all(w >= 0 for w in WEIGHTS.values())


def test_score_weighted() -> None:
    def result(correct: int, wrong: int, unknown: int, extra: int) -> Outcome:
        return {
            "correct": {f"c{i}": "red" for i in range(correct)},
            "wrong": {f"w{i}": "got red, label blue" for i in range(wrong)},
            "unknown": {f"u{i}": "label red" for i in range(unknown)},
            "npc": {},
            "extra": {f"e{i}": "red" for i in range(extra)},
        }

    score = Score()
    score.add(result(8, 1, 1, 0), weight=3.0)
    score.add(result(0, 0, 10, 2), weight=1.0)
    score.add(result(0, 10, 0, 0), weight=0.0)

    assert (score.images, score.correct, score.wrong, score.unknown) == (3, 8, 11, 11)
    assert score.extra == 2
    # rows by weight: 3 * 10 + 1 * 10 + 0 * 10
    assert score.weighted("correct") == pytest.approx(24 / 40)
    assert score.weighted("wrong") == pytest.approx((3 + 2) / 40)
    assert score.weighted("unknown") == pytest.approx((3 + 10) / 40)
    # Kish: (sum w)^2 / sum w^2
    assert score.effective_images == pytest.approx(16 / 10)


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
    # By image weight (tests/data/tabcap_weights.json)
    w_counts: dict[str, float] = field(default_factory=dict)
    w_sum: float = 0.0
    w_sq_sum: float = 0.0

    def add(self, result: Outcome, weight: float) -> None:
        counts = {
            "correct": len(result["correct"]),
            "wrong": len(result["wrong"]),
            "unknown": len(result["unknown"]),
            "extra": len(result["extra"]) + len(result["npc"]),
        }
        self.images += 1
        self.correct += counts["correct"]
        self.wrong += counts["wrong"]
        self.unknown += counts["unknown"]
        self.extra += counts["extra"]
        for k, n in counts.items():
            self.w_counts[k] = self.w_counts.get(k, 0.0) + weight * n
        self.w_sum += weight
        self.w_sq_sum += weight**2

    def weighted(self, kind: str) -> float:
        """Weighted share of rows. wrong includes extra"""
        c = self.w_counts
        rows = c.get("correct", 0) + c.get("wrong", 0) + c.get("unknown", 0)
        n = c.get(kind, 0) + (c.get("extra", 0) if kind == "wrong" else 0)
        return n / rows if rows else float("nan")

    @property
    def effective_images(self) -> float:
        return self.w_sum**2 / self.w_sq_sum if self.w_sq_sum else 0.0

    def line(self, group: str) -> str:
        rows = self.correct + self.wrong + self.unknown

        def pct(n: int) -> str:
            return f"{n / rows:6.1%}" if rows else "     -"

        def wpct(kind: str) -> str:
            return f"{self.weighted(kind):6.1%}" if self.w_sum else "     -"

        # A team for a name not in the list is an error too
        wrong = self.wrong + self.extra
        return (
            f"{group:<34} {self.images:>4} {rows:>5} {pct(self.correct)} "
            f"{pct(wrong)} {pct(self.unknown)} {self.extra:>5} | "
            f"{self.effective_images:5.1f} {wpct('correct')} {wpct('wrong')} "
            f"{wpct('unknown')}"
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
            scores.setdefault(group, Score()).add(result, WEIGHTS[fixture.name])

    header = (
        f"{'group':<34} {'img':>4} {'rows':>5} correct  wrong unknown extra | "
        "w-img w-corr w-wrng w-unkn"
    )
    request.config.stash[REPORT_KEY] = [
        f"--tabcap={selection}, {MANIFEST.version}",
        header,
        *(scores[g].line(g) for g in sorted(scores, key=lambda g: (g != "all", g))),
        "wrong includes extra (a team for an NPC or a name not in the list)",
        "w-*: weighted by how common the setup is (tests/data/tabcap_weights.json); "
        "w-img: effective number of images",
        "Exit criteria: correct >= 85 %, wrong < 2 %",
    ]
