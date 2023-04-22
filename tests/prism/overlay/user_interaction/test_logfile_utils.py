import unittest.mock
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import toml

from prism.overlay.user_interaction.logfile_utils import (
    ActiveLogfile,
    LogfileCache,
    autoselect_logfile,
    create_active_logfiles,
    file_exists,
    get_logfile,
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

    cache = replace(
        cache, known_logfiles=tuple(tmp_path / path for path in cache.known_logfiles)
    )

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


NOT_USED = cast(LogfileCache, None)


@pytest.mark.parametrize(
    "old_cache, logfile_ages_seconds, suggested_logfiles, updated_cache, autoselect, new_cache, result",  # noqa: E501
    (
        (
            LogfileCache(known_logfiles=(), last_used_index=None),
            (),
            (),
            LogfileCache(known_logfiles=(), last_used_index=None),
            True,
            LogfileCache(known_logfiles=(), last_used_index=None),
            None,
        ),
        (
            LogfileCache(known_logfiles=(Path("B"), Path("C")), last_used_index=None),
            (1, 100),
            (),
            LogfileCache(known_logfiles=(Path("A"),), last_used_index=None),
            False,
            LogfileCache(known_logfiles=(Path("B"), Path("C")), last_used_index=None),
            None,
        ),
        (
            LogfileCache(known_logfiles=(), last_used_index=None),
            (),
            (),
            LogfileCache(known_logfiles=(Path("A"),), last_used_index=0),
            True,
            LogfileCache(known_logfiles=(Path("A"),), last_used_index=0),
            Path("A"),
        ),
        (
            LogfileCache(known_logfiles=(Path("A"),), last_used_index=0),
            (1,),
            (),
            NOT_USED,
            True,
            LogfileCache(known_logfiles=(Path("A"),), last_used_index=0),
            Path("A"),
        ),
        (
            LogfileCache(known_logfiles=(Path("A"),), last_used_index=0),
            (1,),
            (),
            LogfileCache(known_logfiles=(Path("B"),), last_used_index=0),
            False,
            LogfileCache(known_logfiles=(Path("B"),), last_used_index=0),
            Path("B"),
        ),
        (
            LogfileCache(known_logfiles=(Path("A"),), last_used_index=0),
            (1, 100),
            (Path("KnownMCLogfile"),),
            NOT_USED,
            True,
            LogfileCache(
                known_logfiles=(Path("A"), Path("KnownMCLogfile")), last_used_index=0
            ),
            Path("A"),
        ),
        (
            LogfileCache(known_logfiles=(Path("A"),), last_used_index=0),
            (1, 10),
            (Path("KnownMCLogfile"),),
            LogfileCache(
                known_logfiles=(Path("A"), Path("KnownMCLogfile")), last_used_index=0
            ),
            False,
            LogfileCache(
                known_logfiles=(Path("A"), Path("KnownMCLogfile")), last_used_index=0
            ),
            Path("A"),
        ),
    ),
)
def test_get_logfile(
    old_cache: LogfileCache,
    logfile_ages_seconds: tuple[float, ...],
    suggested_logfiles: tuple[Path, ...],
    updated_cache: LogfileCache,
    autoselect: bool,
    new_cache: LogfileCache,
    result: Path | None,
) -> None:
    def update_cache(
        active_logfiles: tuple[ActiveLogfile, ...], last_used_id: int | None
    ) -> LogfileCache:
        return updated_cache

    def read_logfile_cache(logfile_cache_path: Path) -> tuple[LogfileCache, bool]:
        return old_cache, False

    def create_active_logfiles(
        known_logfiles: tuple[Path, ...]
    ) -> tuple[ActiveLogfile, ...]:
        return tuple(
            ActiveLogfile(id_=id_, path=path, age_seconds=age)
            for id_, (path, age) in enumerate(
                zip(known_logfiles, logfile_ages_seconds, strict=True)
            )
        )

    # Pass None to make sure we don't accidentally write to disk somewhere
    cache_path = cast(Path, None)
    with unittest.mock.patch(
        "prism.overlay.user_interaction.logfile_utils.create_active_logfiles",
        create_active_logfiles,
    ), unittest.mock.patch(
        "prism.overlay.user_interaction.logfile_utils.write_logfile_cache"
    ) as patched_write_logfile_cache, unittest.mock.patch(
        "prism.overlay.user_interaction.logfile_utils.read_logfile_cache",
        read_logfile_cache,
    ), unittest.mock.patch(
        "prism.overlay.user_interaction.logfile_utils.suggest_logfiles",
        lambda: suggested_logfiles,
    ):
        logfile_path = get_logfile(
            update_cache=update_cache,
            logfile_cache_path=cache_path,
            autoselect=autoselect,
        )

    if logfile_path is None:
        # We don't write to disk if the user doesn't select anything
        assert old_cache == new_cache

    if old_cache == new_cache or logfile_path is None:
        patched_write_logfile_cache.assert_not_called()
    else:
        patched_write_logfile_cache.assert_called_once_with(cache_path, new_cache)

    if logfile_path is None:
        assert new_cache.last_used_index is None
    else:
        assert new_cache.last_used_index is not None
        assert logfile_path == new_cache.known_logfiles[new_cache.last_used_index]
