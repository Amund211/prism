"""
Tabcap test fixtures: labeled tab-list screenshots in the public R2 bucket.

The manifest (tests/data/tabcap_fixtures.json) pins the bucket version,
every fixture name, its sha256 and its split (train / test). Only the
fixtures in the manifest are downloaded and tested.

Local copy: <root>/<version>/<name>.{png,json}, root is $PRISM_TEST_FIXTURES_DIR
or tests/data/r2/ (git-ignored). A version dir in the bucket never changes,
so a local file is trusted and never fetched again. A new version is a new
dir, so it is downloaded again.

Prefetch: python -m tests.tabcap_fixtures [train|test|all]
"""

import hashlib
import http.client
import json
import os
import sys
import time
import urllib.request
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pytest

# Lines for the "tabcap scores" section of the pytest summary
REPORT_KEY = pytest.StashKey[list[str]]()

Split = Literal["train", "test"]
Selection = Literal["train", "test", "all"]

DATA_DIR = Path(__file__).parent / "data"
MANIFEST = DATA_DIR / "tabcap_fixtures.json"
ROOT_ENV = "PRISM_TEST_FIXTURES_DIR"


@dataclass(frozen=True)
class Fixture:
    name: str
    split: Split
    novel: str | None
    sha256: Mapping[str, str]  # by extension: "png", "json"


@dataclass(frozen=True)
class Manifest:
    base_url: str
    version: str
    fixtures: Mapping[str, Fixture]

    def select(self, selection: Selection) -> list[Fixture]:
        return [
            f
            for f in self.fixtures.values()
            if selection == "all" or f.split == selection
        ]


def load_manifest(path: Path = MANIFEST) -> Manifest:
    raw: dict[str, Any] = json.loads(path.read_text())
    return Manifest(
        base_url=raw["base_url"],
        version=raw["version"],
        fixtures={
            name: Fixture(
                name=name,
                split=f["split"],
                novel=f.get("novel"),
                sha256={"png": f["png"], "json": f["json"]},
            )
            for name, f in raw["fixtures"].items()
        },
    )


def local_dir(manifest: Manifest) -> Path:
    root = Path(os.environ.get(ROOT_ENV) or DATA_DIR / "r2")
    return root / manifest.version


def _fetch(url: str, attempts: int = 4) -> bytes:
    # Cloudflare blocks the default Python-urllib user agent
    request = urllib.request.Request(url, headers={"User-Agent": "prism-tests"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data: bytes = response.read()
                return data
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
    # Write then rename: an interrupted run never leaves a partial file
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)


def ensure(manifest: Manifest, fixtures: Iterable[Fixture]) -> Path:
    """Download the missing files of these fixtures. Returns the local dir"""
    directory = local_dir(manifest)
    missing = [
        (f"{manifest.base_url}/{manifest.version}/{path.name}", path, sha)
        for f in fixtures
        for ext, sha in f.sha256.items()
        if not (path := directory / f"{f.name}.{ext}").is_file()
    ]
    if missing:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {len(missing)} tabcap fixture files to {directory}")
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda m: _download(*m), missing))
    return directory


def verify(manifest: Manifest, fixtures: Iterable[Fixture]) -> list[str]:
    """Files whose local sha256 is not the one in the manifest"""
    directory = local_dir(manifest)
    return [
        str(path)
        for f in fixtures
        for ext, sha in f.sha256.items()
        if hashlib.sha256(
            (path := directory / f"{f.name}.{ext}").read_bytes()
        ).hexdigest()
        != sha
    ]


def main(argv: list[str]) -> int:  # pragma: nocover
    selection: Selection = argv[0] if argv else "all"  # type: ignore[assignment]
    manifest = load_manifest()
    fixtures = manifest.select(selection)
    print(ensure(manifest, fixtures))
    bad = verify(manifest, fixtures)
    for path in bad:
        print(f"sha256 mismatch: {path}")
    return 1 if bad else 0


if __name__ == "__main__":  # pragma: nocover
    sys.exit(main(sys.argv[1:]))
