import sys
from pathlib import Path

import pytest

from prism.overlay.directories import (
    PrismDirs,
    ensure_directory,
    get_dirs,
    must_ensure_directory,
)


@pytest.fixture
def clean_dirs_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin $HOME and clear XDG vars so get_dirs() returns deterministic paths."""
    monkeypatch.setenv("HOME", "/home/test")
    for var in (
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_STATE_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-specific paths")
def test_linux_paths(clean_dirs_env: None) -> None:
    config_dir = Path("/home/test/.config/prism_overlay")
    assert get_dirs() == PrismDirs(
        cache_dir=Path("/home/test/.cache/prism_overlay"),
        log_dir=Path("/home/test/.cache/prism_overlay/log"),
        config_dir=config_dir,
        settings_path=config_dir / "settings.toml",
        logfile_cache_path=config_dir / "known_logfiles.toml",
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-specific paths")
def test_macos_paths(clean_dirs_env: None) -> None:
    config_dir = Path("/home/test/Library/Application Support/prism_overlay")
    assert get_dirs() == PrismDirs(
        cache_dir=Path("/home/test/Library/Caches/prism_overlay"),
        log_dir=Path("/home/test/Library/Logs/prism_overlay"),
        config_dir=config_dir,
        settings_path=config_dir / "settings.toml",
        logfile_cache_path=config_dir / "known_logfiles.toml",
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific paths")
def test_windows_paths() -> None:
    base = Path.home() / "AppData" / "Local" / "prism_overlay" / "prism_overlay"
    assert get_dirs() == PrismDirs(
        cache_dir=base / "Cache",
        log_dir=base / "Logs",
        config_dir=base,
        settings_path=base / "settings.toml",
        logfile_cache_path=base / "known_logfiles.toml",
    )


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
