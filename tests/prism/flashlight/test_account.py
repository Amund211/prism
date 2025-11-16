import pytest

from prism.errors import APIError
from prism.flashlight.account import (
    FlashlightAccountProvider,
    parse_flashlight_account,
)
from prism.player import Account
from prism.requests import make_prism_requests_session


def test_make_account_provider() -> None:
    provider = FlashlightAccountProvider(
        retry_limit=3, initial_timeout=1.0, session=make_prism_requests_session()
    )
    assert provider.seconds_until_unblocked == 0.0


@pytest.mark.parametrize(
    "response_json, account",
    # Real responses from Flashlight API with anonymized UUIDs
    (
        (
            {
                "success": True,
                "username": "Player123",
                "uuid": "01234567-89ab-cdef-0123-456789abcdef",
            },
            Account(
                username="Player123",
                uuid="01234567-89ab-cdef-0123-456789abcdef",
            ),
        ),
    ),
)
def test_parse_flashlight_account(response_json: object, account: Account) -> None:
    assert parse_flashlight_account(response_json) == account


@pytest.mark.parametrize(
    "response_json, error",
    (
        (
            # Real response from invalid username length
            {
                "success": False,
                "username": "<invalid>",
                "cause": "invalid username length",
            },
            APIError,
        ),
        (
            # Made up response - not a dict
            "invalid response",
            APIError,
        ),
        (
            # Made up response - missing success
            {
                "uuid": "01234567-89ab-cdef-0123-456789abcdef",
                "username": "Player123",
            },
            APIError,
        ),
        (
            # Made up response - invalid uuid type
            {
                "success": True,
                "uuid": [],
                "username": "Player123",
            },
            APIError,
        ),
        (
            # Made up response - invalid username type
            {
                "success": True,
                "uuid": "01234567-89ab-cdef-0123-456789abcdef",
                "username": [],
            },
            APIError,
        ),
        (
            # Made up response - uuid not a uuid
            {
                "success": True,
                "uuid": "not-a-uuid",
                "username": "Player123",
            },
            APIError,
        ),
    ),
)
def test_parse_flashlight_account_error(
    response_json: object, error: type[Exception]
) -> None:
    with pytest.raises(error):
        parse_flashlight_account(response_json)
