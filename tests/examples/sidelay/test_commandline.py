from typing import Optional, Sequence

import pytest

from examples.sidelay.commandline import Options, get_options, resolve_path

DEFAULT_SETTINGS = "some_settings_file.toml"


def make_options(
    logfile: Optional[str] = None, settings: str = DEFAULT_SETTINGS
) -> Options:
    """Construct an Options instance from its components"""
    return Options(
        logfile_path=resolve_path(logfile) if logfile is not None else None,
        settings_path=resolve_path(settings),
    )


@pytest.mark.parametrize(
    "args, result",
    (
        ([], make_options(None)),
        (["-l", "someotherlogfile"], make_options("someotherlogfile")),
        (["--logfile", "someotherlogfile"], make_options("someotherlogfile")),
        (["-s", "s.toml"], make_options(None, "s.toml")),
        (
            ["-l", "somelogfile", "--settings", "s.toml"],
            make_options("somelogfile", "s.toml"),
        ),
        (
            ["--settings", "s.toml", "-l", "somelogfile"],
            make_options("somelogfile", "s.toml"),
        ),
        # Weird input -> weird output
        (
            ["--settings", "somelogfile.txt", "--logfile", "s.toml"],
            make_options("s.toml", "somelogfile.txt"),
        ),
    ),
)
def test_get_options(args: Sequence[str], result: Options) -> None:
    assert (
        get_options(default_settings_path=resolve_path(DEFAULT_SETTINGS), args=args)
        == result
    )
