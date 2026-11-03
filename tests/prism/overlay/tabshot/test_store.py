from datetime import datetime
from pathlib import Path

from PIL import Image

from prism.overlay.tabshot.capture import Monitor, RawCapture
from prism.overlay.tabshot.store import (
    SampleStore,
    burst_stem,
    capture_filename,
    to_image_rect,
)

CAPTURE = RawCapture(
    bgra=bytes([10, 20, 30, 255]) * 6,
    monitors=(Monitor(-2, 0, 3, 2), Monitor(-2, 0, 2, 2), Monitor(0, 0, 1, 1)),
)


def test_to_image_rect() -> None:
    assert to_image_rect((100, 50, 30, 20), Monitor(-1920, -10, 0, 0)) == (
        2020,
        60,
        30,
        20,
    )


def test_names() -> None:
    now = datetime(2026, 11, 3, 14, 5, 9, 42_999)
    assert burst_stem(now) == "140509.042"
    assert capture_filename("140509.042", 60) == "140509.042-0060ms.png"


def test_save(tmp_path: Path) -> None:
    store = SampleStore(tmp_path / "tabshot")
    directory = store.burst_dir(datetime(2026, 11, 3))
    assert directory == tmp_path / "tabshot" / "2026-11-03"

    store.save_png(directory / "a.png", CAPTURE)
    store.save_json(directory / "a.json", {"x": 1})

    image = Image.open(directory / "a.png")
    assert image.size == (3, 2)
    assert image.getpixel((0, 0)) == (30, 20, 10)
    assert (directory / "a.json").read_text() == '{\n  "x": 1\n}'

    # Existing files are counted on start
    assert SampleStore(tmp_path / "tabshot")._files == 2


def test_full(tmp_path: Path) -> None:
    store = SampleStore(tmp_path, max_files=1)
    assert store.has_space()
    store.save_json(tmp_path / "a.json", {})
    assert not store.has_space()
    assert store.full

    store.save_json(tmp_path / "b.json", {})
    store.save_png(tmp_path / "b.png", CAPTURE)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.json"]

    assert not SampleStore(tmp_path, max_bytes=1).has_space()
