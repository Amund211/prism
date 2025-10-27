import pytest

from prism.errors import APIError
from prism.flashlight import (
    FlashlightTagsProvider,
    parse_flashlight_tags,
    validate_tag_severity,
)
from prism.player import Tags, TagSeverity


def test_make_tags_provider() -> None:
    provider = FlashlightTagsProvider(retry_limit=3, initial_timeout=1.0)
    assert provider.seconds_until_unblocked == 0.0


@pytest.mark.parametrize(
    "raw_severity, validated",
    (
        ("none", "none"),
        ("medium", "medium"),
        ("high", "high"),
        ("invalid", None),
        (None, None),
        (123, None),
    ),
)
def test_validate_tag_severity(
    raw_severity: object, validated: TagSeverity | None
) -> None:
    assert validate_tag_severity(raw_severity) == validated


@pytest.mark.parametrize(
    "response_json, tags",
    # Real responses from Flashlight API with anonymized UUIDs
    (
        (
            {
                "uuid": "01234567-89ab-cdef-0123-456789abcdef",
                "tags": {"cheating": "medium", "sniping": "none"},
            },
            Tags(
                cheating="medium",
                sniping="none",
            ),
        ),
        (
            {
                "uuid": "01234567-89ab-cdef-0123-456789abcdef",
                "tags": {"cheating": "none", "sniping": "none"},
            },
            Tags(
                cheating="none",
                sniping="none",
            ),
        ),
        (
            # Made up response - all high
            {
                "uuid": "01234567-89ab-cdef-0123-456789abcdef",
                "tags": {"cheating": "high", "sniping": "high"},
            },
            Tags(
                cheating="high",
                sniping="high",
            ),
        ),
    ),
)
def test_parse_flashlight_tags(response_json: str, tags: Tags) -> None:
    assert parse_flashlight_tags(response_json) == tags


@pytest.mark.parametrize(
    "response_json, error",
    (
        (
            # Made up response - empty tags
            {
                "uuid": "some-uuid",
                "tags": {},
            },
            APIError,
        ),
        (
            # Made up response - missing cheating
            {
                "uuid": "some-uuid",
                "tags": {
                    "sniping": "high",
                },
            },
            APIError,
        ),
        (
            # Made up response - missing sniping
            {
                "uuid": "some-uuid",
                "tags": {
                    "cheating": "high",
                },
            },
            APIError,
        ),
        (
            # Made up response - bad type on tags
            {"uuid": "some-uuid", "tags": "123"},
            APIError,
        ),
        (
            # Made up response - bad type on tags
            {"uuid": "some-uuid", "tags": None},
            APIError,
        ),
    ),
)
def test_parse_flashlight_tags_error(
    response_json: str, error: type[Exception]
) -> None:
    with pytest.raises(error):
        parse_flashlight_tags(response_json)
