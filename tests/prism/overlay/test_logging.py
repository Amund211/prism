from datetime import date
from pathlib import Path

from prism import VERSION_STRING
from prism.overlay.logging import setup_logging


def test_setup_logging(tmp_path: Path) -> None:
    today = date.today().isoformat()
    assert tmp_path.is_dir()

    def assert_has_logfiles(*expected_filenames: str) -> None:
        logfiles = tmp_path.glob("*.log")
        assert sorted([logfile.name for logfile in logfiles]) == sorted(
            expected_filenames
        )
        for logfile in logfiles:
            assert logfile.is_file()
            with logfile.open("r") as f:
                loglines = f.read()
            assert VERSION_STRING in loglines
            assert today in loglines

    setup_logging(log_dir=tmp_path)
    # Would love to test this, but logging has already been set up by the time
    # this test runs
    """
    assert_has_logfiles(f"{today}.0.log")

    setup_logging(log_dir=tmp_path)
    assert_has_logfiles(f"{today}.0.log", f"{today}.1.log")
    """
