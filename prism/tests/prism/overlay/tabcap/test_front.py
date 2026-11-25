"""
The front step (prism.overlay.tabcap.reader.front) gives the same output as
the lab front it was ported from, on every train fixture.

tests/data/tabcap_front_hashes.json has, per train image, the finder, the
number of name regions and a SHA-256 of the full front output (finder, tab,
parsed rows, name regions, name and row crops). It comes from the lab:
    lab/front_check.py dump <lab dir> <out.json>
on branch tabcap-front-split. Run with:
    uv run pytest tests/prism/overlay/tabcap/test_front.py --tabcap=train
"""

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tests.prism.overlay.tabcap.test_samples import TRAIN, tabcap_dir
from tests.tabcap_fixtures import DATA_DIR

HASHES: dict[str, dict[str, Any]] = json.loads(
    (DATA_DIR / "tabcap_front_hashes.json").read_text()
)

__all__ = ["tabcap_dir"]  # the fixture: --tabcap selection + download


def feed(h: "hashlib._Hash", o: object) -> None:
    """Hash a front value like the lab front_check.py: dataclasses by type
    name and field, arrays with dtype and shape"""
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        h.update(type(o).__name__.encode())
        for f in dataclasses.fields(o):
            h.update(f.name.encode())
            feed(h, getattr(o, f.name))
    elif isinstance(o, np.ndarray):
        h.update(f"nd{o.dtype}{o.shape}".encode())
        h.update(np.ascontiguousarray(o).tobytes())
    elif isinstance(o, (list, tuple)):
        h.update(f"{type(o).__name__}{len(o)}".encode())
        for x in o:
            feed(h, x)
    elif o is None or isinstance(o, (bool, int, float, str, np.generic)):
        h.update(f"{type(o).__name__}:{o!r};".encode())
    else:
        raise TypeError(type(o))


def front_hash(rgb: np.ndarray[Any, Any]) -> dict[str, Any]:
    from prism.overlay.tabcap.reader.front import front, norm_crop, regions_of

    finder, tab, prows = front(rgb)
    h = hashlib.sha256()
    feed(h, (finder, tab, prows))
    n = 0
    if tab is not None:
        k = tab.k
        regions = regions_of(rgb, prows, k)
        n = len(regions)
        feed(h, regions)
        for r in regions:
            row = r.prow.row
            feed(h, norm_crop(rgb, row.y, r.x0, r.x1, k))
            feed(h, norm_crop(rgb, row.y, row.x0, row.x1, k))
    return {"finder": finder, "regions": n, "sha256": h.hexdigest()}


def test_hashes_are_train_split() -> None:
    """The hash file has exactly the train images. Needs no download"""
    assert sorted(HASHES) == sorted(TRAIN)


def test_feed() -> None:
    @dataclasses.dataclass
    class D:
        a: int
        b: list[np.ndarray[Any, Any]]

    def digest(o: object) -> str:
        h = hashlib.sha256()
        feed(h, o)
        return h.hexdigest()

    one = D(1, [np.zeros((2, 2), bool)])
    assert digest(one) == digest(D(1, [np.zeros((2, 2), bool)]))
    assert digest(one) != digest(D(1, [np.zeros((2, 2), np.uint8)]))
    assert digest(one) != digest(D(1, [np.zeros((4,), bool)]))
    assert digest((None, "x", 1.5, (1, 2))) != digest((None, "x", 1.5, [1, 2]))
    with pytest.raises(TypeError):
        digest({1: 2})


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "front_name" in metafunc.fixturenames:
        selected = metafunc.config.getoption("tabcap") in ("train", "all")
        metafunc.parametrize("front_name", TRAIN if selected else [])


def test_front_equals_lab(front_name: str, tabcap_dir: Path) -> None:
    from PIL import Image

    with Image.open(tabcap_dir / f"{front_name}.png") as image:
        rgb = np.asarray(image.convert("RGB"))
    assert front_hash(rgb) == HASHES[front_name]
