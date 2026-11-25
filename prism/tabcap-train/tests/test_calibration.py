"""
Calibration: render the labeled tab list onto the plain shot and compare it
with the real Tab frame (calib.py). Only the tab box counts. Heads, Lunar
icons and badges are cropped from the real frame at the rendered positions;
everything else (background, slots, text, shadow, score, ping) is rendered.

Off by default (download). Run:
    uv run pytest tests/test_calibration.py --synth
Pack fonts: TABCAP_RESOURCE_PACKS=<dir> with fonts/<font id>/ascii.png (+
optional ascii.properties); else those pairs skip. Fonts are never stored in
git or R2.

Ratchet: tests/data/synth_expected.json holds per burst the box,
exact_share (whole box), bg_exact_share (pixels the render leaves as
background) and mean_abs. A test fails when a burst gets worse.
--synth-update writes the current values (after an improvement).
"""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from PIL import Image

from calib import (
    JAR_FONT,
    JAR_ICONS,
    ensure,
    jar_image,
    load_manifest,
    pack_font_path,
)
from synth.canvas import Sprite
from synth.tablist import LUNAR, RenderResult, TabRow, TabSpec, layout, render
from synth.text import BitmapFont, parse_width_properties

MANIFEST = load_manifest()
EXPECTED_PATH = Path(__file__).parent / "data/synth_expected.json"
EXPECTED: dict[str, dict[str, Any]] = json.loads(EXPECTED_PATH.read_text())
DUMMY = Sprite(np.zeros((1, 1, 4), np.uint8), 8, 8)


@pytest.fixture(scope="module")
def calib_dir(request: pytest.FixtureRequest) -> Path:
    if not request.config.getoption("--synth"):
        pytest.skip("synth calibration tests are off; run with --synth")
    return ensure(MANIFEST)


def rgb(path: Path) -> npt.NDArray[np.uint8]:
    return np.asarray(Image.open(path).convert("RGB"))


def crop(real: npt.NDArray[np.uint8], pos: tuple[int, int], k: int) -> Sprite:
    x, y = pos
    t = real[y * k : (y + 8) * k, x * k : (x + 8) * k]
    return Sprite(np.dstack([t, np.full(t.shape[:2], 255, np.uint8)]), 8, 8)


def spec_of(
    label: dict[str, Any], real: npt.NDArray[np.uint8], font: BitmapFont, k: int
) -> TabSpec:
    rows = tuple(
        TabRow(
            text=r["text"],
            score=r["score"],
            ping_ms=r["ping_ms"],
            icon=DUMMY if r["lunar_icon"] else None,
            badge=DUMMY if r["badge"] else None,
        )
        for r in label["rows"]
    )
    spec = TabSpec(
        rows=rows, header=tuple(label["header"]), footer=tuple(label["footer"])
    )
    lay = layout(spec, font, real.shape[1] // k, LUNAR)
    out = []
    for tr, rl in zip(rows, lay.rows):
        assert rl.head is not None
        out.append(
            replace(
                tr,
                head=crop(real, rl.head, k),
                icon=crop(real, rl.icon, k) if rl.icon else None,
                badge=crop(real, rl.badge, k) if rl.badge else None,
            )
        )
    return replace(spec, rows=tuple(out))


def font_for(font_id: str) -> BitmapFont:
    if font_id == "vanilla":
        return BitmapFont(jar_image(MANIFEST, JAR_FONT))
    path = pack_font_path(font_id)
    if path is None:
        pytest.skip(f"pack font {font_id} not available (set TABCAP_RESOURCE_PACKS)")
    # the font bank stores ascii.properties as JSON
    props = path.with_name("ascii.properties.json")
    raw = json.loads(props.read_text()) if props.is_file() else {}
    widths = parse_width_properties("\n".join(f"{k}={v}" for k, v in raw.items()))
    # Lunar: OptiFine HD rules, width.N overrides, faint texels not counted
    tex = np.asarray(Image.open(path).convert("RGBA"))
    return BitmapFont(tex, hd=True, widths=widths, ink_alpha=26)


def metrics(res: RenderResult, real: npt.NDArray[np.uint8]) -> dict[str, Any]:
    x0, y0, x1, y1 = res.box
    a = res.image[y0:y1, x0:x1].astype(int)
    b = real[y0:y1, x0:x1].astype(int)
    eq = (a == b).all(axis=2)
    bg = ~res.ink[y0:y1, x0:x1]
    return {
        "box": list(res.box),
        "exact_share": round(float(eq.mean()), 5),
        "bg_exact_share": round(float(eq[bg].mean()), 5),
        "mean_abs": round(float(np.abs(a - b).mean()), 4),
    }


LABELS_NAME = "labels.json"


@pytest.mark.parametrize("burst", MANIFEST.bursts)
def test_calibration(
    burst: str, calib_dir: Path, request: pytest.FixtureRequest
) -> None:
    label = json.loads((calib_dir / LABELS_NAME).read_text())["bursts"][burst]
    k = label["gui_scale"]
    font = font_for(label["font"])
    icons = Sprite(jar_image(MANIFEST, JAR_ICONS), 256, 256)
    plain = rgb(calib_dir / label["plain"])
    real = rgb(calib_dir / label["frame"])
    spec = spec_of(label, real, font, k)
    res = render(plain, spec, font, k, LUNAR, icons)
    got = metrics(res, real)
    # the box found in the real frame by the pair check (index.json)
    index = json.loads((calib_dir / "index.json").read_text())
    real_box = next(
        f["tab_box"]
        for p in index["pairs"]
        if p["plain"] == label["plain"]
        for f in p["frames"]
        if f["frame"] == label["frame"]
    )
    got["box_matches_real"] = got["box"] == real_box
    if request.config.getoption("--synth-update"):
        EXPECTED[burst] = got
        EXPECTED_PATH.write_text(
            json.dumps(dict(sorted(EXPECTED.items())), indent=2) + "\n"
        )
        return
    want = EXPECTED[burst]
    assert got["box"] == want["box"]
    assert got["box_matches_real"] >= want["box_matches_real"]
    assert got["exact_share"] >= want["exact_share"]
    assert got["bg_exact_share"] >= want["bg_exact_share"]
    assert got["mean_abs"] <= want["mean_abs"]
