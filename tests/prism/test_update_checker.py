from typing import Any

import pytest

from prism.update_checker import _update_available, parse_releases_to_tags

TAGS = ("v2.1.0", "v2.0.0", "v1.0.1", "v1.0.0")


@pytest.mark.parametrize(
    "current_version, tags, result",
    (
        ("v2.1.0", TAGS, False),
        ("v2.0.0", TAGS, True),
        ("v1.0.1", TAGS, True),
        ("v1.0.0", TAGS, True),
        ("v2.1.0", None, False),  # Could not get tags
        ("v1.9.0", TAGS, False),  # Unknown version
        ("v3.1.0", TAGS, False),  # Unknown version
        ("v2.0.0", tuple(reversed(TAGS)), False),  # Order messed up
    ),
)
def test__update_available(
    current_version: str, tags: tuple[str, ...] | None, result: bool
) -> None:
    assert _update_available(current_version, tags) == result


@pytest.mark.parametrize(
    "releases, tags",
    (
        ([{"tag_name": "tag1"}, {"tag_name": "tag2"}], ("tag1", "tag2")),
        ([], ()),
        # Misc broken responses
        ({"message": "Not Found"}, None),  # The 404 response
        ("just a string", None),
        ([{}, {}], None),
    ),
)
def test_parse_releases_to_tags(releases: Any, tags: tuple[str, ...] | None) -> None:
    assert parse_releases_to_tags(releases) == tags
