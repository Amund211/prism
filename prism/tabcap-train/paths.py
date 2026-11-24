"""Input and output paths, from env vars (see README.md)."""

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _env(name: str) -> Path:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"Set {name} (see README.md)")
    return Path(v)


def resource_packs() -> Path:
    """Private font bank: fonts/, vanilla/1.8.9/, README.md"""
    return _env("TABCAP_RESOURCE_PACKS")


def names_file() -> Path:
    """Private real player names, one per line"""
    return _env("TABCAP_NAMES")


def fixtures() -> Path:
    """Root of the fixture dirs; same var and default as the prism tests"""
    v = os.environ.get("PRISM_TEST_FIXTURES_DIR")
    return Path(v) if v else HERE.parent / "tests/data/fixtures"


def results() -> Path:
    """Generated sets, models, logs"""
    v = os.environ.get("TABCAP_RESULTS")
    return Path(v) if v else HERE / "results"
