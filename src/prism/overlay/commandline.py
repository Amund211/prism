import argparse
import logging
from argparse import ArgumentParser
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Options:
    logfile_path: Path | None
    settings_path: Path
    output_to_console: bool
    loglevel: int
    test_ssl: bool


def resolve_path(p: str) -> Path:  # pragma: no cover
    """Construct the path from p and resolve it to lock the effects of cwd"""
    return Path(p).resolve()


def get_options(
    default_settings_path: Path, args: Sequence[str] | None = None
) -> Options:
    # We pass args manually in testing -> don't exit on error
    parser = ArgumentParser(exit_on_error=args is None)

    parser.add_argument(
        "-l",
        "--logfile",
        help="Path to launcher_log.txt",
        type=resolve_path,
        default=None,
    )

    parser.add_argument(
        "-s",
        "--settings",
        help="Path to the .toml settings-file",
        type=resolve_path,
        default=default_settings_path,
    )

    parser.add_argument(
        "-q",
        "--quiet",
        help="Don't print the stats table to stdout",
        action="store_true",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        help="Verbosity of the logs (0-5). 0 means info, 1-5 means critical-debug",
        action="count",
        default=0,
    )

    # Used for testing ssl certificate patching
    parser.add_argument(
        "--test-ssl",
        help=argparse.SUPPRESS,
        action="store_true",
    )

    # Parse the args
    # Parses from sys.argv if args is None
    parsed = parser.parse_args(args=args)

    assert parsed.logfile is None or isinstance(parsed.logfile, Path)
    assert isinstance(parsed.settings, Path)
    assert isinstance(parsed.quiet, bool)
    assert isinstance(parsed.verbose, int)
    assert isinstance(parsed.test_ssl, bool)

    if parsed.verbose <= 0:
        # Default loglevel to INFO
        loglevel = logging.INFO
    elif parsed.verbose == 1:
        loglevel = logging.CRITICAL
    elif parsed.verbose == 2:
        loglevel = logging.ERROR
    elif parsed.verbose == 3:
        loglevel = logging.WARNING
    elif parsed.verbose == 4:
        loglevel = logging.INFO
    elif parsed.verbose >= 5:
        loglevel = logging.DEBUG

    return Options(
        logfile_path=parsed.logfile,
        settings_path=parsed.settings,
        output_to_console=not parsed.quiet,
        loglevel=loglevel,
        test_ssl=parsed.test_ssl,
    )
