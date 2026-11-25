"""Train-split fixtures only: training must never read the test split."""

import json
from functools import cache

import numpy as np
from PIL import Image

from paths import HERE, fixtures

MANIFEST = HERE.parent / "tests/data/tabcap_fixtures.json"
SPLIT = "train"


@cache
def manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def train_names() -> list[str]:
    m = manifest()
    return sorted(n for n, f in m["fixtures"].items() if f["split"] == SPLIT)


def label(name: str) -> dict:
    assert manifest()["fixtures"][name]["split"] == SPLIT, name
    return json.loads((fixtures() / manifest()["version"] / f"{name}.json").read_text())


def image(name: str) -> np.ndarray:
    assert manifest()["fixtures"][name]["split"] == SPLIT, name
    with Image.open(fixtures() / manifest()["version"] / f"{name}.png") as im:
        return np.asarray(im.convert("RGB"))
