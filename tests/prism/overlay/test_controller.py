from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from prism.errors import APIError, APIKeyError, APIThrottleError, PlayerNotFoundError
from prism.overlay.controller import ERROR_DURING_PROCESSING
from prism.player import MISSING_WINSTREAKS, Winstreaks
from prism.ssl_errors import MissingLocalIssuerSSLError
from tests.prism.overlay.utils import (
    MockedAccountProvider,
    MockedPlayerProvider,
    MockedWinstreakProvider,
    assert_not_called,
    create_controller,
    make_settings,
)


def test_real_overlay_controller() -> None:
    controller = create_controller(
        settings=make_settings(
            antisniper_api_key="antisniper_key",
            use_antisniper_api=True,
        ),
    )

    assert controller.antisniper_key_holder is not None
    assert controller.antisniper_key_holder.key == "antisniper_key"


def test_real_overlay_controller_no_antisniper_key() -> None:
    controller = create_controller(
        settings=make_settings(
            antisniper_api_key=None,
            use_antisniper_api=True,
        ),
    )

    assert controller.antisniper_key_holder is None


def test_real_overlay_controller_get_uuid() -> None:
    error: Exception | None = None
    returned_uuid: str = ""

    def get_uuid_mock(username: str) -> str:
        assert username == "username"
        if error:
            raise error

        return returned_uuid

    controller = create_controller(
        settings=make_settings(
            antisniper_api_key="antisniper_key",
            use_antisniper_api=True,
            user_id="1234",
        ),
        account_provider=MockedAccountProvider(get_uuid_for_username=get_uuid_mock),
    )

    error = APIError()
    uuid = controller.get_uuid("username")
    assert uuid is ERROR_DURING_PROCESSING

    error = PlayerNotFoundError()
    uuid = controller.get_uuid("username")
    assert uuid is None

    error = MissingLocalIssuerSSLError()
    assert not controller.missing_local_issuer_certificate
    uuid = controller.get_uuid("username")
    assert uuid is ERROR_DURING_PROCESSING
    assert controller.missing_local_issuer_certificate

    error = None
    returned_uuid = "uuid"
    uuid = controller.get_uuid("username")
    assert uuid is returned_uuid

    assert not controller.missing_local_issuer_certificate


def test_real_overlay_controller_get_playerdata() -> None:
    error: Exception | None = None
    returned_playerdata: Mapping[str, object] = {}

    def mock_get_playerdata(uuid: str, user_id: str) -> Mapping[str, object]:
        assert uuid == "uuid"
        assert user_id == "1234"

        if error:
            raise error

        return returned_playerdata

    def mock_get_time_ns() -> int:
        return 1234567890123456789

    controller = create_controller(
        settings=make_settings(
            antisniper_api_key="antisniper_key",
            use_antisniper_api=True,
            user_id="1234",
        ),
        player_provider=MockedPlayerProvider(
            get_playerdata_for_uuid=mock_get_playerdata
        ),
        get_time_ns=mock_get_time_ns,
    )
    error = APIError()
    _, playerdata = controller.get_playerdata("uuid")
    assert playerdata is ERROR_DURING_PROCESSING

    error = PlayerNotFoundError()
    _, playerdata = controller.get_playerdata("uuid")
    assert playerdata is None

    error = APIKeyError()
    assert not controller.antisniper_api_key_invalid
    _, playerdata = controller.get_playerdata("uuid")
    assert playerdata is ERROR_DURING_PROCESSING
    assert controller.antisniper_api_key_invalid

    error = APIThrottleError()
    assert not controller.antisniper_api_key_throttled
    _, playerdata = controller.get_playerdata("uuid")
    assert playerdata is ERROR_DURING_PROCESSING
    assert controller.antisniper_api_key_throttled

    error = MissingLocalIssuerSSLError()
    assert not controller.missing_local_issuer_certificate
    _, playerdata = controller.get_playerdata("uuid")
    assert playerdata is ERROR_DURING_PROCESSING
    assert controller.missing_local_issuer_certificate

    error = None
    dataReceivedAtMs, playerdata = controller.get_playerdata("uuid")

    assert playerdata is returned_playerdata
    assert dataReceivedAtMs == 1234567890123456789 // 1_000_000

    assert not controller.antisniper_api_key_invalid
    assert not controller.antisniper_api_key_throttled
    assert not controller.missing_local_issuer_certificate


def test_real_overlay_controller_get_uuid_dependency_injection() -> None:
    """Test that OverlayController uses injected get_uuid function"""
    custom_uuid = "custom-uuid-12345"

    def custom_get_uuid(username: str) -> str:
        assert username == "testuser"
        return custom_uuid

    controller = create_controller(
        account_provider=MockedAccountProvider(get_uuid_for_username=custom_get_uuid)
    )

    result = controller.get_uuid("testuser")
    assert result == custom_uuid


def test_real_overlay_controller_get_playerdata_dependency_injection() -> None:
    """Test that OverlayController uses injected get_playerdata function"""
    custom_playerdata = {"custom": "data", "uuid": "test-uuid"}

    def custom_get_playerdata(uuid: str, user_id: str) -> Mapping[str, object]:
        assert uuid == "test-uuid"
        assert user_id == "test-user-id"
        return custom_playerdata

    def custom_get_time_ns() -> int:
        return 9876543210987654321

    controller = create_controller(
        settings=make_settings(user_id="test-user-id"),
        player_provider=MockedPlayerProvider(
            get_playerdata_for_uuid=custom_get_playerdata
        ),
        get_time_ns=custom_get_time_ns,
    )

    timestamp, result = controller.get_playerdata("test-uuid")
    assert result is custom_playerdata
    assert timestamp == 9876543210987654321 // 1_000_000


def test_real_overlay_controller_get_estimated_winstreaks_dependency_injection() -> (
    None
):
    """Test that OverlayController uses injected get_estimated_winstreaks
    function"""
    custom_winstreaks = Winstreaks(overall=5, solo=3, doubles=2, threes=1, fours=0)
    custom_accurate = True

    def custom_get_estimated_winstreaks(
        uuid: str, antisniper_api_key: str
    ) -> tuple[Winstreaks, bool]:
        assert uuid == "test-uuid"
        assert antisniper_api_key == "test-api-key"
        return custom_winstreaks, custom_accurate

    controller = create_controller(
        settings=make_settings(
            antisniper_api_key="test-api-key",
            use_antisniper_api=True,
        ),
        winstreak_provider=MockedWinstreakProvider(
            get_estimated_winstreaks_for_uuid=custom_get_estimated_winstreaks,
        ),
    )

    winstreaks, accurate = controller.get_estimated_winstreaks("test-uuid")
    assert winstreaks == custom_winstreaks
    assert accurate == custom_accurate


def test_real_overlay_controller_get_estimated_winstreaks_no_api() -> None:
    """Test that OverlayController returns MISSING_WINSTREAKS when
    antisniper API is disabled"""
    controller = create_controller(
        settings=make_settings(
            antisniper_api_key="test-api-key",
            use_antisniper_api=False,  # API is disabled
        ),
        winstreak_provider=MockedWinstreakProvider(
            get_estimated_winstreaks_for_uuid=assert_not_called,
        ),
    )

    winstreaks, accurate = controller.get_estimated_winstreaks("test-uuid")
    assert winstreaks == MISSING_WINSTREAKS
    assert accurate is False


def test_real_overlay_controller_get_estimated_winstreaks_no_key() -> None:
    """Test that OverlayController returns MISSING_WINSTREAKS when no API
    key is set"""
    controller = create_controller(
        settings=make_settings(
            antisniper_api_key=None,  # No API key
            use_antisniper_api=True,
        ),
        winstreak_provider=MockedWinstreakProvider(
            get_estimated_winstreaks_for_uuid=assert_not_called,
        ),
    )

    winstreaks, accurate = controller.get_estimated_winstreaks("test-uuid")
    assert winstreaks == MISSING_WINSTREAKS
    assert accurate is False


@dataclass
class Flags:
    antisniper_api_key_invalid: bool = False
    antisniper_api_key_throttled: bool = False
    missing_local_issuer_certificate: bool = False


@pytest.mark.parametrize(
    "before_flags, error, result_flags",
    [
        (
            Flags(
                antisniper_api_key_invalid=False,
                antisniper_api_key_throttled=True,
                missing_local_issuer_certificate=True,
            ),
            APIKeyError(),
            Flags(
                antisniper_api_key_invalid=True,
                antisniper_api_key_throttled=False,
                missing_local_issuer_certificate=False,
            ),
        ),
        (
            Flags(
                antisniper_api_key_invalid=True,
                antisniper_api_key_throttled=False,
                missing_local_issuer_certificate=True,
            ),
            APIThrottleError(),
            Flags(
                antisniper_api_key_invalid=False,
                antisniper_api_key_throttled=True,
                missing_local_issuer_certificate=False,
            ),
        ),
        (
            Flags(
                antisniper_api_key_invalid=True,
                antisniper_api_key_throttled=True,
                missing_local_issuer_certificate=False,
            ),
            MissingLocalIssuerSSLError(),
            Flags(
                antisniper_api_key_invalid=True,
                antisniper_api_key_throttled=True,
                missing_local_issuer_certificate=True,
            ),
        ),
        # API error does not touch the flags
        (
            Flags(
                antisniper_api_key_invalid=True,
                antisniper_api_key_throttled=True,
                missing_local_issuer_certificate=True,
            ),
            APIError(),
            Flags(
                antisniper_api_key_invalid=True,
                antisniper_api_key_throttled=True,
                missing_local_issuer_certificate=True,
            ),
        ),
        (
            Flags(
                antisniper_api_key_invalid=False,
                antisniper_api_key_throttled=False,
                missing_local_issuer_certificate=False,
            ),
            APIError(),
            Flags(
                antisniper_api_key_invalid=False,
                antisniper_api_key_throttled=False,
                missing_local_issuer_certificate=False,
            ),
        ),
    ],
)
def test_real_overlay_controller_get_estimated_winstreaks_error_handling(
    before_flags: Flags, error: Exception, result_flags: Flags
) -> None:
    """Test that OverlayController handles errors from get_estimated_winstreaks"""

    def get_estimated_winstreaks(
        uuid: str, antisniper_api_key: str
    ) -> tuple[Winstreaks, bool]:
        assert uuid == "test-uuid"
        assert antisniper_api_key == "test-api-key"

        raise error

    controller = create_controller(
        settings=make_settings(
            antisniper_api_key="test-api-key",
            use_antisniper_api=True,
        ),
        winstreak_provider=MockedWinstreakProvider(
            get_estimated_winstreaks_for_uuid=get_estimated_winstreaks
        ),
    )

    controller.antisniper_api_key_invalid = before_flags.antisniper_api_key_invalid
    controller.antisniper_api_key_throttled = before_flags.antisniper_api_key_throttled
    controller.missing_local_issuer_certificate = (
        before_flags.missing_local_issuer_certificate
    )

    winstreaks, accurate = controller.get_estimated_winstreaks("test-uuid")
    assert winstreaks == MISSING_WINSTREAKS
    assert accurate is False
    assert (
        controller.antisniper_api_key_invalid == result_flags.antisniper_api_key_invalid
    )
    assert (
        controller.antisniper_api_key_throttled
        == result_flags.antisniper_api_key_throttled
    )
    assert (
        controller.missing_local_issuer_certificate
        == result_flags.missing_local_issuer_certificate
    )


def test_real_overlay_controller_get_time_ns_dependency_injection() -> None:
    """Test that OverlayController uses injected get_time_ns function"""
    custom_time_ns = 1234567890123456789

    def custom_get_time_ns() -> int:
        return custom_time_ns

    custom_playerdata = {"test": "data", "uuid": "test-uuid"}

    def custom_get_playerdata(uuid: str, user_id: str) -> Mapping[str, object]:
        assert uuid == "test-uuid"
        assert user_id == "test-user-id"
        return custom_playerdata

    controller = create_controller(
        settings=make_settings(user_id="test-user-id"),
        player_provider=MockedPlayerProvider(
            get_playerdata_for_uuid=custom_get_playerdata
        ),
        get_time_ns=custom_get_time_ns,
    )

    timestamp, result = controller.get_playerdata("test-uuid")
    assert result is custom_playerdata
    assert timestamp == custom_time_ns // 1_000_000  # Should use injected time function
