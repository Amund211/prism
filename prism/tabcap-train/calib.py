"""
Calibration pairs for the synth generator (synth/): the same scene without
(F9 plain shot) and with the tab list (Tab burst frame), in the public R2
bucket, plus fitted labels (labels.json). c2_comp uses the train plain shots
as backgrounds; tests/test_calibration.py uses the pairs.

The manifest (calib.json) pins the bucket version and the sha256 of every
file. Fonts are never stored: the vanilla font and icons.png come from the
Mojang 1.8.9 client jar (pinned by sha1, fetched on use); a pack font is read
from $TABCAP_RESOURCE_PACKS/fonts/<font id>/ascii.png, else its pairs skip.

Local copy: <fixtures root>/<version>/ (paths.fixtures()).
Prefetch: python calib.py
"""

import hashlib
import http.client
import io
import json
import os
import sys
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from paths import HERE, fixtures

MANIFEST = HERE / "calib.json"
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


def _fetch(url: str, attempts: int = 4) -> bytes:
    # Cloudflare blocks the default Python-urllib user agent
    request = urllib.request.Request(url, headers={"User-Agent": "prism-tests"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except OSError, http.client.HTTPException:
            if attempt == attempts - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def _download(url: str, dest: Path, sha256: str) -> None:
    data = _fetch(url)
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        raise ValueError(f"{url}: sha256 {got}, manifest has {sha256}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)


def ensure(manifest: SynthManifest | None = None) -> Path:
    """Download the missing files. Returns the local version dir"""
    manifest = manifest or load_manifest()
    directory = fixtures() / manifest.version
    missing = [
        (f"{manifest.base_url}/{manifest.version}/{name}", directory / name, sha)
        for name, sha in manifest.files.items()
        if not (directory / name).is_file()
    ]
    if missing:
        print(f"Downloading {len(missing)} synth calibration files to {directory}")
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda m: _download(*m), missing))
    return directory


def jar(manifest: SynthManifest) -> Path:
    """The Mojang 1.8.9 client jar, fetched once and checked by sha1"""
    path = fixtures() / "mojang" / f"{manifest.jar_sha1}.jar"
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


def jar_image(manifest: SynthManifest, member: str) -> np.ndarray:
    with zipfile.ZipFile(jar(manifest)) as z:
        return np.asarray(Image.open(io.BytesIO(z.read(member))).convert("RGBA"))


@cache
def pack_font_path(font_id: str) -> Path | None:
    base = os.environ.get("TABCAP_RESOURCE_PACKS")
    if not base:
        return None
    path = Path(base) / "fonts" / font_id / "ascii.png"
    return path if path.is_file() else None


def main() -> int:
    manifest = load_manifest()
    print(ensure(manifest))
    print(jar(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
