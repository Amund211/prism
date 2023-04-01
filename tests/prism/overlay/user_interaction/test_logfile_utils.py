from pathlib import Path

from prism.overlay.user_interaction.logfile_utils import (
    file_exists,
    get_timestamp,
    suggest_logfiles,
)


def test_file_exists_no() -> None:
    assert not file_exists("ThisPathDoesNotExists")
    assert not file_exists(Path("ThisPathDoesNotExists"))


def test_file_exists_yes(tmp_path: Path) -> None:
    # A directory is not a file
    assert not file_exists(str(tmp_path))
    assert not file_exists(tmp_path)
    file_path = tmp_path / "newfile"

    with file_path.open("w") as f:
        f.write("hi")

    assert file_exists(str(file_path))
    assert file_exists(file_path)


def test_suggest_logfiles() -> None:
    suggestions = suggest_logfiles()
    assert all(map(file_exists, suggestions))


def test_get_timestamp(tmp_path: Path) -> None:
    file_path = tmp_path / "newfile"

    with file_path.open("w") as f:
        f.write("hi")

    assert get_timestamp(str(file_path)) == file_path.stat().st_mtime

    assert get_timestamp(str(tmp_path / "doesnotexist")) == 0
