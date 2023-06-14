from typing import Any

import pytest

from prism.update_checker import (
    VersionInfo,
    _update_available,
    parse_releases_to_latest_tag,
)


@pytest.mark.parametrize(
    "version_string, result",
    (
        ("v1.0.0", VersionInfo(1, 0, 0, False)),
        ("v1.0.1", VersionInfo(1, 0, 1, False)),
        ("v1.1.1", VersionInfo(1, 1, 1, False)),
        ("v2.1.1", VersionInfo(2, 1, 1, False)),
        ("v1.3.1-dev", VersionInfo(1, 3, 1, True)),
        ("v1.3.1-lol", VersionInfo(1, 3, 1, True)),
        # Invalid strings
        ("v1.2.3.4.5", None),
        ("va.b.c", None),
    ),
)
def test_versioninfo_parse(version_string: str, result: VersionInfo | None) -> None:
    assert VersionInfo.parse(version_string) == result


@pytest.mark.parametrize(
    "current_string, latest_string, minor_bump, patch_bump",
    (
        ("v2.1.0", "v2.1.0", False, False),
        ("v2.0.0", "v2.1.0", True, True),
        ("v1.0.1", "v2.1.0", True, True),
        ("v1.0.0", "v2.1.0", True, True),
        ("v2.1.0", "v2.1.1", False, True),
        ("v1.0.1-dev", "v1.0.1", False, True),
        ("v2.1.0", None, False, False),  # Could not get tags
        ("InvalidVersion", "InvalidVersion", False, False),  # Fails to parse
    ),
)
def test__update_available(
    current_string: str, latest_string: str | None, minor_bump: bool, patch_bump: bool
) -> None:
    assert (
        _update_available(current_string, latest_string, ignore_patch_bumps=True)
        == minor_bump
    )
    assert (
        _update_available(current_string, latest_string, ignore_patch_bumps=False)
        == patch_bump
    )


@pytest.mark.parametrize(
    "releases, latest_tag",
    (
        ([{"tag_name": "tag1"}, {"tag_name": "tag2"}], "tag1"),
        ([], None),
        # Misc broken responses
        ({"message": "Not Found"}, None),  # The 404 response
        ("just a string", None),
        ([{}, {}], None),
        (["no dict here"], None),
    ),
)
def test_parse_releases_to_latest_tag(releases: Any, latest_tag: str | None) -> None:
    assert parse_releases_to_latest_tag(releases) == latest_tag
