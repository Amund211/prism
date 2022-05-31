import logging
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


@dataclass
class Options:
    logfile_path: Optional[Path]
    settings_path: Path
    output_to_console: bool
    loglevel: int
    threads: int


def resolve_path(p: str) -> Path:  # pragma: no cover
    """Construct the path from p and resolve it to lock the effects of cwd"""
    return Path(p).resolve()


def get_options(
    default_settings_path: Path, args: Optional[Sequence[str]] = None
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
        "-v", "--verbose", help="Verbosity of the logs (0-4)", action="count", default=0
    )

    parser.add_argument(
        "-t",
        "--threads",
        help="Number of threads for getting stats",
        type=int,
        default=16,
    )

    # Parse the args
    # Parses from sys.argv if args is None
    parsed = parser.parse_args(args=args)

    assert parsed.logfile is None or isinstance(parsed.logfile, Path)
    assert isinstance(parsed.settings, Path)
    assert isinstance(parsed.quiet, bool)
    assert isinstance(parsed.verbose, int)
    assert isinstance(parsed.threads, int)

    if parsed.verbose <= 0:
        loglevel = logging.CRITICAL
    elif parsed.verbose == 1:
        loglevel = logging.ERROR
    elif parsed.verbose == 2:
        loglevel = logging.WARNING
    elif parsed.verbose == 3:
        loglevel = logging.INFO
    elif parsed.verbose >= 4:
        loglevel = logging.DEBUG

    return Options(
        logfile_path=parsed.logfile,
        settings_path=parsed.settings,
        output_to_console=not parsed.quiet,
        loglevel=loglevel,
        threads=parsed.threads,
    )
