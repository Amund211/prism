import string

from prism import USER_AGENT, VERSION_STRING
from prism.update_checker import VersionInfo


def test_version_string() -> None:
    """
    Assert proper formatting of the version string: v<major>.<minor>.<patch>(-<descr>)

    We use the version string in the filename of the compiled binary in gh actions.
    Make sure that works by not including any special characters
    """

    # No special characters
    assert set(VERSION_STRING).issubset(f"v{string.digits}.-{string.ascii_letters}")

    # Version starts with v
    assert VERSION_STRING[0] == "v"

    main_version, *rest = VERSION_STRING[1:].split("-")

    major, minor, patch = main_version.split(".")

    # Properly formatted numbers
    for number in (major, minor, patch):
        assert str(int(number)) == number

    # Assert that it is parsed correctly by VersionInfo.parse
    version_info = VersionInfo.parse(VERSION_STRING)

    assert version_info is not None

    for parsed, raw in (
        (version_info.major, major),
        (version_info.minor, minor),
        (version_info.patch, patch),
    ):
        assert parsed == int(raw)

    assert version_info.dev == bool(rest)


def test_user_agent() -> None:
    """Assert proper formatting of the user agent: prism/<version> (+<url>)"""

    assert len(USER_AGENT.split(" ")) == 2
    version, url = USER_AGENT.split(" ")

    assert version.startswith("prism/")
    assert version.split("/")[1] == VERSION_STRING[1:]

    assert url == "(+https://github.com/Amund211/prism)"
