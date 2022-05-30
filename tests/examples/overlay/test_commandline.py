import pytest

from examples.overlay.commandline import Options, get_options, resolve_path

DEFAULT_SETTINGS = "some_settings_file.toml"


def make_options(
    logfile: str | None = None,
    settings: str = DEFAULT_SETTINGS,
    output_to_console: bool = True,
) -> Options:
    """Construct an Options instance from its components"""
    return Options(
        logfile_path=resolve_path(logfile) if logfile is not None else None,
        settings_path=resolve_path(settings),
        output_to_console=output_to_console,
    )


@pytest.mark.parametrize(
    "commandline, result",
    (
        ("", make_options()),
        ("-q", make_options(output_to_console=False)),
        ("-l someotherlogfile", make_options("someotherlogfile")),
        ("--logfile someotherlogfile", make_options("someotherlogfile")),
        ("-s s.toml", make_options(None, settings="s.toml")),
        (
            "-l somelogfile --settings s.toml",
            make_options("somelogfile", settings="s.toml"),
        ),
        (
            "--settings s.toml -l somelogfile",
            make_options("somelogfile", settings="s.toml"),
        ),
        (
            "--settings s.toml -l somelogfile --quiet",
            make_options("somelogfile", settings="s.toml", output_to_console=False),
        ),
        # Weird input -> weird output
        (
            "--settings somelogfile.txt --logfile s.toml",
            make_options("s.toml", settings="somelogfile.txt"),
        ),
    ),
)
def test_get_options(commandline: str, result: Options) -> None:
    assert (
        get_options(
            default_settings_path=resolve_path(DEFAULT_SETTINGS),
            args=commandline.split(" ") if commandline else [],
        )
        == result
    )
