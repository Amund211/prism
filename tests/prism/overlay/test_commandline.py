import logging

import pytest

from prism.overlay.commandline import Options, get_options, resolve_path

DEFAULT_SETTINGS = "some_settings_file.toml"


def make_options(
    logfile: str | None = None,
    settings: str = DEFAULT_SETTINGS,
    loglevel: int = logging.INFO,
    test_ssl: bool = False,
    test: bool = False,
) -> Options:
    """Construct an Options instance from its components"""
    return Options(
        logfile_path=resolve_path(logfile) if logfile is not None else None,
        settings_path=resolve_path(settings),
        loglevel=loglevel,
        test_ssl=test_ssl,
        test=test,
    )


test_cases: tuple[tuple[str, Options], ...] = (
    # No options
    ("", make_options()),
    # Logging verbosity
    ("--verbose", make_options(loglevel=logging.CRITICAL)),
    ("-v", make_options(loglevel=logging.CRITICAL)),
    ("-vv", make_options(loglevel=logging.ERROR)),
    ("-vvv", make_options(loglevel=logging.WARNING)),
    ("-vvvv", make_options(loglevel=logging.INFO)),
    ("-vvvvv", make_options(loglevel=logging.DEBUG)),
    ("-vvvvvv", make_options(loglevel=logging.DEBUG)),  # Too many v's
    # Logfile
    ("-l someotherlogfile", make_options("someotherlogfile")),
    ("--logfile someotherlogfile", make_options("someotherlogfile")),
    # Settings
    ("-s s.toml", make_options(settings="s.toml")),
    # Test ssl
    ("--test-ssl", make_options(test_ssl=True)),
    # Test
    ("--test", make_options(test=True)),
    # Multiple arguments
    (
        "-l somelogfile --settings s.toml",
        make_options("somelogfile", settings="s.toml"),
    ),
    (
        "--settings s.toml -l somelogfile",
        make_options("somelogfile", settings="s.toml"),
    ),
    (
        "--settings s.toml -l somelogfile --quiet -vvvvv --test-ssl --test",
        make_options(
            "somelogfile",
            settings="s.toml",
            loglevel=logging.DEBUG,
            test_ssl=True,
            test=True,
        ),
    ),
    # Weird input -> weird output
    (
        "--settings somelogfile.txt --logfile s.toml",
        make_options("s.toml", settings="somelogfile.txt"),
    ),
)


@pytest.mark.parametrize("commandline, result", test_cases)
def test_get_options(commandline: str, result: Options) -> None:
    assert (
        get_options(
            default_settings_path=resolve_path(DEFAULT_SETTINGS),
            args=commandline.split(" ") if commandline else [],
        )
        == result
    )
