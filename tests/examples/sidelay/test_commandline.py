from argparse import ArgumentError
from typing import Sequence

import pytest

from examples.sidelay.commandline import Options, get_options, resolve_path

DEFAULT_SETTINGS = "some_settings_file.toml"


def make_options(logfile: str, settings: str = DEFAULT_SETTINGS) -> Options:
    """Construct an Options instance from its components"""
    return Options(
        logfile_path=resolve_path(logfile), settings_path=resolve_path(settings)
    )


@pytest.mark.parametrize(
    "args, result",
    (
        (["somelogfile"], make_options("somelogfile")),
        (["someotherlogfile"], make_options("someotherlogfile")),
        (["somelogfile", "-s", "s.toml"], make_options("somelogfile", "s.toml")),
        (
            ["somelogfile", "--settings", "s.toml"],
            make_options("somelogfile", "s.toml"),
        ),
        (
            ["--settings", "s.toml", "somelogfile"],
            make_options("somelogfile", "s.toml"),
        ),
        # Weird input -> weird output
        (
            ["--settings", "somelogfile.txt", "s.toml"],
            make_options("s.toml", "somelogfile.txt"),
        ),
    ),
)
def test_get_options(args: Sequence[str], result: Options) -> None:
    assert (
        get_options(default_settings_path=resolve_path(DEFAULT_SETTINGS), args=args)
        == result
    )


@pytest.mark.parametrize(
    "args",
    (
        # Empty commandline not allowed - logfile required
        ([],),
    ),
)
def test_get_options_errors(args: Sequence[str]) -> None:
    with pytest.raises(ArgumentError):
        get_options(default_settings_path=resolve_path(DEFAULT_SETTINGS), args=args)
