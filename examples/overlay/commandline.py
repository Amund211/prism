from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


@dataclass
class Options:
    logfile_path: Optional[Path]
    settings_path: Path
    output_to_console: bool


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
        "-p",
        "--print",
        help="Additionally print the stats table to stdout",
        action="store_true",
    )

    # Parse the args
    # Parses from sys.argv if args is None
    parsed = parser.parse_args(args=args)

    assert parsed.logfile is None or isinstance(parsed.logfile, Path)
    assert isinstance(parsed.settings, Path)
    assert isinstance(parsed.print, bool)

    return Options(
        logfile_path=parsed.logfile,
        settings_path=parsed.settings,
        output_to_console=parsed.print,
    )
