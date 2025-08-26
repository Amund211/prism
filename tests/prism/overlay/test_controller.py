from collections.abc import Mapping

from prism.errors import APIError, APIKeyError, APIThrottleError, PlayerNotFoundError
from prism.overlay.antisniper_api import AntiSniperAPIKeyHolder
from prism.overlay.controller import ERROR_DURING_PROCESSING
from prism.player import MISSING_WINSTREAKS, Winstreaks
from prism.ratelimiting import RateLimiter
from prism.ssl_errors import MissingLocalIssuerSSLError
from tests.prism.overlay.utils import (
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
        get_uuid=get_uuid_mock,
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

    def mock_get_playerdata(
        uuid: str,
        user_id: str,
        key_holder: AntiSniperAPIKeyHolder | None,
        api_limiter: RateLimiter,
    ) -> Mapping[str, object]:
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
        get_playerdata=mock_get_playerdata,
        get_time_ns=mock_get_time_ns,
    )
    error = APIError()
    _, playerdata = controller.get_playerdata("uuid")
    assert playerdata is ERROR_DURING_PROCESSING

    error = PlayerNotFoundError()
    _, playerdata = controller.get_playerdata("uuid")
    assert playerdata is None

    error = APIKeyError()
    assert not controller.api_key_invalid
    _, playerdata = controller.get_playerdata("uuid")
    assert playerdata is ERROR_DURING_PROCESSING
    assert controller.api_key_invalid

    error = APIThrottleError()
    assert not controller.api_key_throttled
    _, playerdata = controller.get_playerdata("uuid")
    assert playerdata is ERROR_DURING_PROCESSING
    assert controller.api_key_throttled

    error = MissingLocalIssuerSSLError()
    assert not controller.missing_local_issuer_certificate
    _, playerdata = controller.get_playerdata("uuid")
    assert playerdata is ERROR_DURING_PROCESSING
    assert controller.missing_local_issuer_certificate

    error = None
    dataReceivedAtMs, playerdata = controller.get_playerdata("uuid")

    assert playerdata is returned_playerdata
    assert dataReceivedAtMs == 1234567890123456789 // 1_000_000

    assert not controller.api_key_invalid
    assert not controller.api_key_throttled
    assert not controller.missing_local_issuer_certificate


def test_real_overlay_controller_get_uuid_dependency_injection() -> None:
    """Test that OverlayController uses injected get_uuid function"""
    custom_uuid = "custom-uuid-12345"

    def custom_get_uuid(username: str) -> str:
        assert username == "testuser"
        return custom_uuid

    controller = create_controller(get_uuid=custom_get_uuid)

    result = controller.get_uuid("testuser")
    assert result == custom_uuid


def test_real_overlay_controller_get_playerdata_dependency_injection() -> None:
    """Test that OverlayController uses injected get_playerdata function"""
    custom_playerdata = {"custom": "data", "uuid": "test-uuid"}

    def custom_get_playerdata(
        uuid: str,
        user_id: str,
        key_holder: AntiSniperAPIKeyHolder | None,
        api_limiter: RateLimiter,
    ) -> Mapping[str, object]:
        assert uuid == "test-uuid"
        assert user_id == "test-user-id"
        return custom_playerdata

    def custom_get_time_ns() -> int:
        return 9876543210987654321

    controller = create_controller(
        settings=make_settings(user_id="test-user-id"),
        get_playerdata=custom_get_playerdata,
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
        uuid: str, key_holder: AntiSniperAPIKeyHolder
    ) -> tuple[Winstreaks, bool]:
        assert uuid == "test-uuid"
        assert key_holder.key == "test-api-key"
        return custom_winstreaks, custom_accurate

    controller = create_controller(
        settings=make_settings(
            antisniper_api_key="test-api-key",
            use_antisniper_api=True,
        ),
        get_estimated_winstreaks=custom_get_estimated_winstreaks,
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
        get_estimated_winstreaks=assert_not_called,
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
        get_estimated_winstreaks=assert_not_called,
    )

    winstreaks, accurate = controller.get_estimated_winstreaks("test-uuid")
    assert winstreaks == MISSING_WINSTREAKS
    assert accurate is False


def test_real_overlay_controller_get_time_ns_dependency_injection() -> None:
    """Test that OverlayController uses injected get_time_ns function"""
    custom_time_ns = 1234567890123456789

    def custom_get_time_ns() -> int:
        return custom_time_ns

    custom_playerdata = {"test": "data", "uuid": "test-uuid"}

    def custom_get_playerdata(
        uuid: str,
        user_id: str,
        key_holder: AntiSniperAPIKeyHolder | None,
        api_limiter: RateLimiter,
    ) -> Mapping[str, object]:
        assert uuid == "test-uuid"
        assert user_id == "test-user-id"
        return custom_playerdata

    controller = create_controller(
        settings=make_settings(user_id="test-user-id"),
        get_playerdata=custom_get_playerdata,
        get_time_ns=custom_get_time_ns,
    )

    timestamp, result = controller.get_playerdata("test-uuid")
    assert result is custom_playerdata
    assert timestamp == custom_time_ns // 1_000_000  # Should use injected time function
