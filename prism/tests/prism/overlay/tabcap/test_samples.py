"""
Team recognition on the labeled R2 fixtures (tests/tabcap_fixtures.py).

Off by default (download + minutes of CPU). Run one of:
    uv run pytest tests/prism/overlay/tabcap/test_samples.py --tabcap=train
    ... --tabcap=test
    ... --tabcap=all

Train / test split (prototype plan, "Training and test data"):
- train: one test per image, asserts the exact result in
  tests/data/tabcap_expected.json, plus the summary scores. Algorithm work
  looks at these only.
- test: the summary scores only, no per-image results. Do not tune on them.
- all: both, on all fixtures. For the final check.
--tabcap-update writes the current per-image results as the expected ones.
"""

import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass
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

# Hypixel team letters; "." = no team read
LETTER = {
    "red": "r",
    "blue": "b",
    "green": "g",
    "yellow": "y",
    "aqua": "a",
    "white": "w",
    "pink": "p",
    "gray": "s",
}


@dataclass(frozen=True)
class Result:
    # One letter per label row, so no player names are stored in the repo
    rows: str
    # Known names that are not in the list (dead / left) but got a team
    extra: int


_results: dict[str, tuple[dict[str, Any], Result]] = {}
_updates: dict[str, Result] = {}


def _selection(config: pytest.Config) -> Selection | None:
    selection: Selection | None = config.getoption("tabcap")
    return selection


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "fixture_name" in metafunc.fixturenames:
        selection = _selection(metafunc.config)
        names = (
            [f.name for f in MANIFEST.select(selection)]
            if selection in ("train", "all")
            else []
        )
        metafunc.parametrize("fixture_name", names)


@pytest.fixture(scope="module")
def tabcap_dir(request: pytest.FixtureRequest) -> Iterator[Path]:
    selection = _selection(request.config)
    if selection is None:
        pytest.skip("pass --tabcap=train|test|all")
    yield ensure(MANIFEST, MANIFEST.select(selection))

    if _updates:
        old = json.loads(EXPECTED.read_text()) if EXPECTED.is_file() else {}
        new = {**old, **{n: asdict(r) for n, r in _updates.items()}}
        EXPECTED.write_text(json.dumps(dict(sorted(new.items())), indent=1) + "\n")


def _run(name: str, directory: Path) -> tuple[dict[str, Any], Result]:
    if name not in _results:
        from PIL import Image

        from prism.overlay.tabcap.teams import read_teams

        label: dict[str, Any] = json.loads((directory / f"{name}.json").read_text())
        with Image.open(directory / f"{name}.png") as image:
            got = read_teams(image, label["known"])

        names = [row["name"] for row in label["rows"]]
        rows = "".join(LETTER[t] if (t := got.get(n)) else "." for n in names)
        extra = len(set(got) - set(names))
        _results[name] = (label, Result(rows, extra))
    return _results[name]


def test_fixture(
    fixture_name: str, tabcap_dir: Path, request: pytest.FixtureRequest
) -> None:  # pragma: nocover
    label, result = _run(fixture_name, tabcap_dir)
    if request.config.getoption("tabcap_update"):
        _updates[fixture_name] = result
        return

    raw = json.loads(EXPECTED.read_text()).get(fixture_name)
    assert raw is not None, "no expected result: run with --tabcap-update"
    expected = Result(**raw)
    diff = [
        f"{row['name']}: label {row['team']}, expected {e}, got {g}"
        for row, e, g in zip(label["rows"], expected.rows, result.rows)
        if e != g
    ]
    assert (diff, result.extra) == ([], expected.extra)


@dataclass
class Score:
    images: int = 0
    correct: int = 0
    wrong: int = 0
    unknown: int = 0
    extra: int = 0

    def add(self, label: dict[str, Any], result: Result) -> None:
        self.images += 1
        self.extra += result.extra
        for row, got in zip(label["rows"], result.rows):
            if row.get("npc") or row.get("covered") or row["team"] is None:
                continue
            if got == ".":
                self.unknown += 1
            elif got == LETTER[row["team"]]:
                self.correct += 1
            else:
                self.wrong += 1

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
            scores.setdefault(group, Score()).add(label, result)

    header = f"{'group':<34} {'img':>4} {'rows':>5} correct  wrong unknown extra"
    request.config.stash[REPORT_KEY] = [
        f"--tabcap={selection}, {MANIFEST.version}",
        header,
        *(scores[g].line(g) for g in sorted(scores, key=lambda g: (g != "all", g))),
        "Exit criteria: correct >= 85 %, wrong < 2 % (extra counts as wrong)",
    ]
