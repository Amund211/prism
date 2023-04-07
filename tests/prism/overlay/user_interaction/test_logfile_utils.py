from pathlib import Path
from typing import Any

import pytest
import toml

from prism.overlay.user_interaction.logfile_utils import (
    ActiveLogfile,
    LogfileCache,
    autoselect_logfile,
    compare_active_logfiles,
    create_active_logfiles,
    file_exists,
    get_timestamp,
    read_logfile_cache,
    refresh_active_logfiles,
    safe_resolve_existing_path,
    suggest_logfiles,
    write_logfile_cache,
)


def test_file_exists_no() -> None:
    assert not file_exists("ThisPathDoesNotExists")
    assert not file_exists(Path("ThisPathDoesNotExists"))
    assert safe_resolve_existing_path("ThisPathDoesNotExists") is None


def test_file_exists_yes(tmp_path: Path) -> None:
    # A directory is not a file
    assert not file_exists(str(tmp_path))
    assert not file_exists(tmp_path)
    file_path = (tmp_path / "newfile").resolve()

    with file_path.open("w") as f:
        f.write("hi")

    assert file_exists(str(file_path))
    assert file_exists(file_path)
    assert safe_resolve_existing_path(str(file_path)) == file_path


def test_suggest_logfiles() -> None:
    suggestions = suggest_logfiles()
    assert all(map(file_exists, suggestions))


def test_get_timestamp(tmp_path: Path) -> None:
    file_path = tmp_path / "newfile"

    with file_path.open("w") as f:
        f.write("hi")

    assert get_timestamp(file_path) == file_path.stat().st_mtime

    assert get_timestamp(tmp_path / "doesnotexist") == 0


def test_active_logfile(tmp_path: Path) -> None:
    file_path = tmp_path / "newfile"

    with file_path.open("w") as f:
        f.write("hi")

    active_logfile = ActiveLogfile(id_=0, path=file_path, age_seconds=100)
    assert not active_logfile.recent
    assert not active_logfile.really_recent
    assert active_logfile.get_age_interval(interval_length=10) == 10

    for refreshed in (
        ActiveLogfile.with_age(id_=0, path=file_path),
        active_logfile.refresh_age(),
    ):
        assert refreshed.recent
        assert refreshed.really_recent

    active_logfiles = create_active_logfiles((file_path,))
    assert len(active_logfiles) == 1
    assert active_logfiles[0].path == file_path
    assert active_logfiles[0].id_ == 0

    refreshed_active_logfiles = refresh_active_logfiles(active_logfiles)
    assert len(refreshed_active_logfiles) == 1
    assert refreshed_active_logfiles[0].path == file_path
    assert refreshed_active_logfiles[0].id_ == 0


SOME_PATH = Path()


@pytest.mark.parametrize(
    "active_logfiles, selected_id, last_used_id, result_index",
    (
        ((), 0, None, None),
        ((ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=1),), 0, None, None),
        ((ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=1),), 0, 5, None),
        ((ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=1),), 0, 0, 0),
        (
            (
                ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=1),
                ActiveLogfile(id_=2, path=SOME_PATH, age_seconds=10),
            ),
            0,
            0,
            None,
        ),
        (
            (
                ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=1),
                ActiveLogfile(id_=2, path=SOME_PATH, age_seconds=100),
            ),
            0,
            0,
            0,
        ),
    ),
)
def test_autoselect_logfile(
    active_logfiles: tuple[ActiveLogfile, ...],
    selected_id: int,
    last_used_id: int | None,
    result_index: int | None,
) -> None:
    result = autoselect_logfile(active_logfiles, selected_id, last_used_id)
    if result_index is None:
        assert result is None
    else:
        assert result is active_logfiles[result_index]


@pytest.mark.parametrize(
    "a, b, equal",
    (
        ((), (), True),
        (
            (ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=1),),
            (ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=1),),
            True,
        ),
        (
            (ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=1),),
            (ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=4),),
            True,
        ),
        (
            (ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=9),),
            (ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=11),),
            True,
        ),
        (
            (
                ActiveLogfile(id_=0, path=Path("a"), age_seconds=1),
                ActiveLogfile(id_=1, path=Path("b"), age_seconds=11),
            ),
            (
                ActiveLogfile(id_=0, path=Path("a"), age_seconds=2),
                ActiveLogfile(id_=1, path=Path("b"), age_seconds=12),
            ),
            True,
        ),
        (
            (ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=1),),
            (ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=6),),
            False,  # No longer really recent
        ),
        (
            (ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=50),),
            (ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=70),),
            False,  # No longer recent
        ),
        (
            (ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=1),),
            (),
            False,  # Missing element
        ),
        (
            (ActiveLogfile(id_=0, path=SOME_PATH, age_seconds=1),),
            (ActiveLogfile(id_=1, path=SOME_PATH, age_seconds=1),),
            False,  # New id
        ),
        (
            (ActiveLogfile(id_=0, path=Path("a"), age_seconds=1),),
            (ActiveLogfile(id_=0, path=Path("b"), age_seconds=1),),
            False,  # New path
        ),
        (
            (ActiveLogfile(id_=0, path=Path("a"), age_seconds=1),),
            (ActiveLogfile(id_=1, path=Path("b"), age_seconds=1),),
            False,  # New ActiveLogfile
        ),
        (
            (
                ActiveLogfile(id_=0, path=Path("a"), age_seconds=1),
                ActiveLogfile(id_=1, path=Path("b"), age_seconds=1),
            ),
            (
                ActiveLogfile(id_=1, path=Path("b"), age_seconds=1),
                ActiveLogfile(id_=0, path=Path("a"), age_seconds=1),
            ),
            False,  # New sort order
        ),
    ),
)
def test_compare_active_logfiles(
    a: tuple[ActiveLogfile, ...], b: tuple[ActiveLogfile, ...], equal: bool
) -> None:
    assert compare_active_logfiles(a, b) is equal


@pytest.mark.parametrize(
    "cache_content, cache, logfile_cache_updated",
    (
        # Ill formed
        ({}, LogfileCache(known_logfiles=(), last_used_index=None), True),
        (
            # Invalid data
            {"known_logfiles": "nope", "last_used": 1234},
            LogfileCache(known_logfiles=(), last_used_index=None),
            True,
        ),
        (
            # Last used logfile not present in known_logfiles
            {"known_logfiles": ("1", "2"), "last_used": "3"},
            LogfileCache(known_logfiles=(Path("1"), Path("2")), last_used_index=None),
            True,
        ),
        (
            # Duplicate known logfiles
            {"known_logfiles": ("1", "1", "1", "1", "1", "2", "3"), "last_used": "1"},
            LogfileCache(
                known_logfiles=(Path("1"), Path("2"), Path("3")), last_used_index=0
            ),
            True,
        ),
        (
            # Missing known logfile
            {"known_logfiles": ("1", "2", "missing_file"), "last_used": "1"},
            LogfileCache(known_logfiles=(Path("1"), Path("2")), last_used_index=0),
            True,
        ),
        (
            # Missing known logfile and last used
            {"known_logfiles": ("1", "2", "missing_file"), "last_used": "missing_file"},
            LogfileCache(known_logfiles=(Path("1"), Path("2")), last_used_index=None),
            True,
        ),
        (
            # Missing known logfile early
            {"known_logfiles": ("missing_file", "1", "2"), "last_used": "1"},
            LogfileCache(known_logfiles=(Path("1"), Path("2")), last_used_index=0),
            True,
        ),
        # Well formed
        (
            {"known_logfiles": ("1", "2", "3"), "last_used": "1"},
            LogfileCache(
                known_logfiles=(Path("1"), Path("2"), Path("3")), last_used_index=0
            ),
            False,
        ),
        (
            {"known_logfiles": ("1", "2", "3"), "last_used": "2"},
            LogfileCache(
                known_logfiles=(Path("1"), Path("2"), Path("3")), last_used_index=1
            ),
            False,
        ),
    ),
)
def test_read_logfile_cache(
    cache_content: dict[str, Any],
    cache: LogfileCache,
    logfile_cache_updated: bool,
    tmp_path: Path,
    monkeypatch: "pytest.MonkeyPatch",
) -> None:
    monkeypatch.chdir(tmp_path)
    logfile_cache_path = tmp_path / "logfile_cache.toml"

    with logfile_cache_path.open("w") as f:
        toml.dump(cache_content, f)

    for filename in ("1", "2", "3"):
        with (tmp_path / filename).open("w") as f:
            f.write("hi")

    cache.known_logfiles = tuple(tmp_path / path for path in cache.known_logfiles)

    assert (cache, logfile_cache_updated) == read_logfile_cache(logfile_cache_path)


def test_read_logfile_cache_invalid_toml(tmp_path: Path) -> None:
    logfile_cache_path = tmp_path / "logfile_cache.toml"

    with logfile_cache_path.open("w") as f:
        f.write(r"[unclosed tag\n")

    assert read_logfile_cache(logfile_cache_path) == (
        LogfileCache(known_logfiles=(), last_used_index=None),
        True,
    )


@pytest.mark.parametrize(
    "cache_content, cache",
    (
        (
            {"known_logfiles": []},
            LogfileCache(known_logfiles=(), last_used_index=None),
        ),
        (
            {"known_logfiles": ["1", "2"]},
            LogfileCache(known_logfiles=(Path("1"), Path("2")), last_used_index=None),
        ),
        (
            {"known_logfiles": ["1", "2", "3"], "last_used": "1"},
            LogfileCache(
                known_logfiles=(Path("1"), Path("2"), Path("3")), last_used_index=0
            ),
        ),
        (
            {"known_logfiles": ["1", "2", "3"], "last_used": "2"},
            LogfileCache(
                known_logfiles=(Path("1"), Path("2"), Path("3")), last_used_index=1
            ),
        ),
    ),
)
def test_write_logfile_cache(
    cache_content: dict[str, Any],
    cache: LogfileCache,
    tmp_path: Path,
) -> None:
    logfile_cache_path = tmp_path / "logfile_cache.toml"

    write_logfile_cache(logfile_cache_path, cache)
    with logfile_cache_path.open("r") as f:
        assert toml.load(f) == cache_content
