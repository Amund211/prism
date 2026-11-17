"""Train-split fixtures only. Never loads test images."""

import json
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "prism/tests/data/tabcap_fixtures.json"
WEIGHTS = ROOT / "prism/tests/data/tabcap_weights.json"
FIXTURES = Path.home() / "git/overlay/test-fixtures"


@cache
def manifest() -> dict:
    return json.loads(MANIFEST.read_text())


@cache
def load_weights() -> dict[str, float]:
    """How common each fixture's setup is (see the prism test summary)"""
    return json.loads(WEIGHTS.read_text())["weights"]


def train_names() -> list[str]:
    m = manifest()
    return sorted(n for n, f in m["fixtures"].items() if f["split"] == "train")


def fixture_dir() -> Path:
    return FIXTURES / manifest()["version"]


def label(name: str) -> dict:
    assert manifest()["fixtures"][name]["split"] == "train", name
    return json.loads((fixture_dir() / f"{name}.json").read_text())


def image(name: str) -> np.ndarray:
    assert manifest()["fixtures"][name]["split"] == "train", name
    with Image.open(fixture_dir() / f"{name}.png") as im:
        return np.asarray(im.convert("RGB"))
