from pathlib import Path

import pytest

from prism.overlay.directories import ensure_directory, must_ensure_directory


def test_ensure_directory(tmp_path: Path) -> None:
    path = tmp_path / "my_dir"

    assert not path.exists()

    assert ensure_directory(path)

    assert path.exists()
    assert path.is_dir()


def test_ensure_directory_doesnt_crash(tmp_path: Path) -> None:
    exists = tmp_path / "exists.txt"
    assert not exists.exists()
    exists.touch()
    assert exists.exists()

    assert not ensure_directory(exists)

    assert exists.exists()
    assert not exists.is_dir()


def test_must_ensure_directory(tmp_path: Path) -> None:
    path = tmp_path / "my_dir"

    assert not path.exists()

    must_ensure_directory(path)

    assert path.exists()
    assert path.is_dir()


def test_must_ensure_directory_raises(tmp_path: Path) -> None:
    exists = tmp_path / "exists.txt"
    assert not exists.exists()
    exists.touch()
    assert exists.exists()

    with pytest.raises(RuntimeError):
        must_ensure_directory(exists)

    assert exists.exists()
    assert not exists.is_dir()
