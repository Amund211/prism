from prism import USER_AGENT, VERSION_STRING


def test_version_string() -> None:
    """
    Assert proper formatting of the version string: v<major>.<minor>.<patch>(-dev)

    We use the version string in the filename of the compiled binary in gh actions.
    Make sure that works by not including any special characters
    """

    # No special characters
    assert set(VERSION_STRING).issubset("v0123456789.-dev")

    # Version starts with v
    assert VERSION_STRING[0] == "v"

    main_version, *rest = VERSION_STRING[1:].split("-")

    # Only allowed suffix is -dev
    assert rest == [] or rest == ["dev"]

    major, minor, patch = main_version.split(".")

    # Properly formatted numbers
    for number in (major, minor, patch):
        assert str(int(number)) == number


def test_user_agent() -> None:
    """Assert proper formatting of the user agent: prism/<version> (+<url>)"""

    assert len(USER_AGENT.split(" ")) == 2
    version, url = USER_AGENT.split(" ")

    assert version.startswith("prism/")
    assert version.split("/")[1] == VERSION_STRING[1:]

    assert url == "(+https://github.com/Amund211/prism)"
