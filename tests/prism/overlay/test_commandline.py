import logging

import pytest

from prism.overlay.commandline import Options, get_options, resolve_path

DEFAULT_SETTINGS = "some_settings_file.toml"


def make_options(
    logfile: str | None = None,
    settings: str = DEFAULT_SETTINGS,
    output_to_console: bool = True,
    loglevel: int = logging.INFO,
    threads: int = 16,
) -> Options:
    """Construct an Options instance from its components"""
    return Options(
        logfile_path=resolve_path(logfile) if logfile is not None else None,
        settings_path=resolve_path(settings),
        output_to_console=output_to_console,
        loglevel=loglevel,
        threads=threads,
    )


test_cases: tuple[tuple[str, Options], ...] = (
    # No options
    ("", make_options()),
    # Output to console
    ("-q", make_options(output_to_console=False)),
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
    # Threads
    ("-t 8", make_options(threads=8)),
    ("--threads=8", make_options(threads=8)),
    ("--threads 8", make_options(threads=8)),
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
        "--settings s.toml -l somelogfile --quiet -vvvvv",
        make_options(
            "somelogfile",
            settings="s.toml",
            output_to_console=False,
            loglevel=logging.DEBUG,
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
