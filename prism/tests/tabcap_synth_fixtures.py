"""
Calibration pairs for the synthetic tab list (prism.overlay.tabcap.synth):
the same scene without (F9 plain shot) and with the tab list (Tab burst
frame), in the public R2 bucket, plus fitted labels (labels.json).

The manifest (tests/data/tabcap_synth_calib.json) pins the bucket version and
the sha256 of every file. Fonts are never stored: the vanilla font and
icons.png come from the Mojang 1.8.9 client jar (pinned by sha1, fetched at
test time); a pack font is read from $PRISM_TABCAP_FONTS_DIR/<font id>/ascii.png
when that dir exists (local resource_packs/fonts), else its pairs are skipped.

Local copy: same root as tests/tabcap_fixtures.py.
Prefetch: python -m tests.tabcap_synth_fixtures
"""

import hashlib
import io
import json
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image

from tests.tabcap_fixtures import DATA_DIR, ROOT_ENV, _download, _fetch

MANIFEST = DATA_DIR / "tabcap_synth_calib.json"
FONTS_ENV = "PRISM_TABCAP_FONTS_DIR"
JAR_FONT = "assets/minecraft/textures/font/ascii.png"
JAR_ICONS = "assets/minecraft/textures/gui/icons.png"


@dataclass(frozen=True)
class SynthManifest:
    base_url: str
    version: str
    files: dict[str, str]  # name -> sha256
    jar_url: str
    jar_sha1: str
    bursts: list[str]  # labeled bursts (keys of labels.json)


def load_manifest(path: Path = MANIFEST) -> SynthManifest:
    raw: dict[str, Any] = json.loads(path.read_text())
    return SynthManifest(
        base_url=raw["base_url"],
        version=raw["version"],
        files=raw["files"],
        bursts=raw["bursts"],
        jar_url=raw["mojang_client"]["url"],
        jar_sha1=raw["mojang_client"]["sha1"],
    )


def root() -> Path:
    return Path(os.environ.get(ROOT_ENV) or DATA_DIR / "fixtures")


def ensure(manifest: SynthManifest) -> Path:
    """Download the missing files. Returns the local version dir"""
    directory = root() / manifest.version
    missing = [
        (f"{manifest.base_url}/{manifest.version}/{name}", directory / name, sha)
        for name, sha in manifest.files.items()
        if not (directory / name).is_file()
    ]
    if missing:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {len(missing)} synth calibration files to {directory}")
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda m: _download(*m), missing))
    return directory


def jar(manifest: SynthManifest) -> Path:
    """The Mojang 1.8.9 client jar, fetched once and checked by sha1"""
    path = root() / "mojang" / f"{manifest.jar_sha1}.jar"
    if not path.is_file():
        data = _fetch(manifest.jar_url)
        got = hashlib.sha1(data).hexdigest()
        if got != manifest.jar_sha1:
            raise ValueError(
                f"{manifest.jar_url}: sha1 {got}, manifest has {manifest.jar_sha1}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return path


def jar_image(manifest: SynthManifest, member: str) -> npt.NDArray[np.uint8]:
    with zipfile.ZipFile(jar(manifest)) as z:
        return np.asarray(Image.open(io.BytesIO(z.read(member))).convert("RGBA"))


@cache
def pack_font_path(font_id: str) -> Path | None:
    base = os.environ.get(FONTS_ENV)
    if not base:
        return None
    path = Path(base) / font_id / "ascii.png"
    return path if path.is_file() else None


def main() -> int:  # pragma: nocover
    manifest = load_manifest()
    print(ensure(manifest))
    print(jar(manifest))
    return 0


if __name__ == "__main__":  # pragma: nocover
    sys.exit(main())
