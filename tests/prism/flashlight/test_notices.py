import pytest

from prism.flashlight.notices import (
    FlashlightNotice,
    _parse_flashlight_notices,
)

CURRENT_TIME_SECONDS = 123.456


def mock_get_time_seconds() -> float:
    return CURRENT_TIME_SECONDS


@pytest.mark.parametrize(
    "response, expected",
    (
        (
            # Real response from flashlight during testing
            {
                "notices": [
                    {
                        "message": "1 dot info w link",
                        "url": "https://prismoverlay.com",
                        "severity": "info",
                        "duration_seconds": 7,
                    },
                    {"message": "Mini user warning", "severity": "warning"},
                    {"message": "Version 1.10 critical notice", "severity": "critical"},
                ]
            },
            (
                FlashlightNotice(
                    message="1 dot info w link",
                    severity="info",
                    url="https://prismoverlay.com",
                    created_at_seconds=CURRENT_TIME_SECONDS,
                    duration_seconds=7,
                ),
                FlashlightNotice(
                    message="Mini user warning",
                    severity="warning",
                    url=None,
                    created_at_seconds=CURRENT_TIME_SECONDS,
                    duration_seconds=None,
                ),
                FlashlightNotice(
                    message="Version 1.10 critical notice",
                    severity="critical",
                    url=None,
                    created_at_seconds=CURRENT_TIME_SECONDS,
                    duration_seconds=None,
                ),
            ),
        ),
        (
            {
                "notices": [
                    {"message": "Info message", "severity": "info", "url": None},
                    {
                        "message": "Warning message",
                        "severity": "warning",
                        "url": "https://example.com/warning",
                    },
                    {
                        "message": "Critical message",
                        "severity": "critical",
                        "duration_seconds": 12.5,
                    },
                ],
            },
            (
                FlashlightNotice(
                    message="Info message",
                    severity="info",
                    url=None,
                    created_at_seconds=CURRENT_TIME_SECONDS,
                    duration_seconds=None,
                ),
                FlashlightNotice(
                    message="Warning message",
                    severity="warning",
                    url="https://example.com/warning",
                    created_at_seconds=CURRENT_TIME_SECONDS,
                    duration_seconds=None,
                ),
                FlashlightNotice(
                    message="Critical message",
                    severity="critical",
                    url=None,
                    created_at_seconds=CURRENT_TIME_SECONDS,
                    duration_seconds=12.5,
                ),
            ),
        ),
        (
            {
                "notices": [
                    {"message": "Valid info", "severity": "info"},
                    {"msg": "Missing message key", "severity": "warning"},
                    {"message": "Invalid severity", "severity": "super severe!!"},
                    {"message": "Invalid url", "severity": "critical", "url": 12345},
                    {
                        "message": "Invalid duration",
                        "severity": "critical",
                        "duration_seconds": "invalid",
                    },
                    "Not a dict",
                ],
            },
            (
                FlashlightNotice(
                    message="Valid info",
                    severity="info",
                    url=None,
                    created_at_seconds=CURRENT_TIME_SECONDS,
                    duration_seconds=None,
                ),
            ),
        ),
        (
            {
                "missing notices key": [],
            },
            (),
        ),
        (
            {
                "notices": "Not a list",
            },
            (),
        ),
        (
            "Not a dict",
            (),
        ),
        (
            [],
            (),
        ),
    ),
)
def test_parse_information(
    response: object, expected: tuple[FlashlightNotice, ...]
) -> None:
    assert _parse_flashlight_notices(response, mock_get_time_seconds) == expected


def test_notice_active() -> None:
    current_time = 100.0

    def get_time_seconds() -> float:
        return current_time

    notice = FlashlightNotice.create(
        message="Test notice",
        severity="info",
        url=None,
        duration_seconds=10.0,
        get_time_seconds=get_time_seconds,
    )

    assert notice.active

    for t in [0.0, 5.0, 9.9]:
        current_time = 100.0 + t
        assert notice.active

    current_time = 110.1
    assert not notice.active


def test_notice_no_duration_active() -> None:
    current_time = 100.0

    def get_time_seconds() -> float:
        return current_time

    notice_no_duration = FlashlightNotice.create(
        message="Test notice no duration",
        severity="info",
        url=None,
        duration_seconds=None,
        get_time_seconds=get_time_seconds,
    )

    assert notice_no_duration.active

    current_time = 1000.0

    assert notice_no_duration.active
