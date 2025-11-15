from dataclasses import dataclass

import pytest

from prism.errors import APIError, APIKeyError, APIThrottleError, PlayerNotFoundError
from prism.overlay.controller import ERROR_DURING_PROCESSING
from prism.player import MISSING_WINSTREAKS, KnownPlayer, Stats, Tags, Winstreaks
from prism.ssl_errors import MissingLocalIssuerSSLError
from tests.prism.overlay.utils import (
    MockedAccountProvider,
    MockedPlayerProvider,
    MockedTagsProvider,
    MockedWinstreakProvider,
    assert_not_called,
    create_controller,
    make_settings,
)


def test_overlay_controller_get_uuid() -> None:
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
    assert uuid == returned_uuid

    assert not controller.missing_local_issuer_certificate


def test_overlay_controller_get_player() -> None:
    error: Exception | None = None
    returned_player = KnownPlayer(
        dataReceivedAtMs=1_234_567_890_123,
        username="TestPlayer",
        uuid="uuid",
        stars=100.0,
        stats=Stats(
            index=1000.0,
            fkdr=2.5,
            kdr=1.5,
            bblr=3.0,
            wlr=2.0,
            winstreak=5,
            winstreak_accurate=True,
            kills=100,
            finals=200,
            beds=150,
            wins=80,
        ),
    )

    def mock_get_player(uuid: str, user_id: str) -> KnownPlayer:
        assert uuid == "uuid"
        assert user_id == "1234"

        if error:
            raise error

        # Return the player with a literal timestamp
        return returned_player

    controller = create_controller(
        settings=make_settings(
            antisniper_api_key="antisniper_key",
            use_antisniper_api=True,
            user_id="1234",
        ),
        player_provider=MockedPlayerProvider(get_player=mock_get_player),
    )
    error = APIError()
    player = controller.get_player("uuid")
    assert player is ERROR_DURING_PROCESSING

    error = PlayerNotFoundError()
    player = controller.get_player("uuid")
    assert player is None

    error = APIKeyError()
    player = controller.get_player("uuid")
    assert player is ERROR_DURING_PROCESSING

    error = APIThrottleError()
    player = controller.get_player("uuid")
    assert player is ERROR_DURING_PROCESSING

    error = MissingLocalIssuerSSLError()
    assert not controller.missing_local_issuer_certificate
    player = controller.get_player("uuid")
    assert player is ERROR_DURING_PROCESSING
    assert controller.missing_local_issuer_certificate

    error = None
    assert controller.get_player("uuid") == returned_player
    assert not controller.missing_local_issuer_certificate


def test_overlay_controller_get_tags() -> None:
    error: Exception | None = None
    returned_tags = Tags(sniping="medium", cheating="none")

    def get_tags_mock(username: str, user_id: str, urchin_api_key: str | None) -> Tags:
        assert username == "username"
        assert user_id == "1234"
        assert urchin_api_key is None
        if error:
            raise error

        return returned_tags

    controller = create_controller(
        settings=make_settings(
            user_id="1234",
        ),
        tags_provider=MockedTagsProvider(get_tags=get_tags_mock),
    )

    error = APIError()
    uuid = controller.get_tags("username")
    assert uuid is ERROR_DURING_PROCESSING
    assert not controller.urchin_api_key_invalid

    error = None
    uuid = controller.get_tags("username")
    assert uuid == returned_tags
    assert not controller.urchin_api_key_invalid


def test_overlay_controller_get_tags_with_api_key() -> None:
    """Test urchin API key flag behavior when an API key is configured.

    The flag should be set to True when APIKeyError occurs with a key.
    The flag should be set to False on success with a key.
    Note: When the flag is True, we don't pass the key, so we won't
    clear the flag until the user updates their key in settings.
    """
    error: Exception | None = None
    expected_api_key: str | None = None
    returned_tags = Tags(sniping="medium", cheating="none")

    def get_tags_mock(username: str, user_id: str, urchin_api_key: str | None) -> Tags:
        assert username == "username"
        assert user_id == "1234"
        assert urchin_api_key == expected_api_key
        if error:
            raise error

        return returned_tags

    controller = create_controller(
        settings=make_settings(
            user_id="1234",
            urchin_api_key="01234567-89ab-cdef-0123-456789abcdef",
        ),
        tags_provider=MockedTagsProvider(get_tags=get_tags_mock),
    )

    # Test with valid key - should succeed and clear flag
    error = None
    expected_api_key = "01234567-89ab-cdef-0123-456789abcdef"
    assert not controller.urchin_api_key_invalid
    tags = controller.get_tags("username")
    assert tags == returned_tags
    assert not controller.urchin_api_key_invalid

    # Test with invalid key - should set flag to True
    error = APIKeyError()
    expected_api_key = "01234567-89ab-cdef-0123-456789abcdef"
    tags = controller.get_tags("username")
    assert tags is ERROR_DURING_PROCESSING
    assert controller.urchin_api_key_invalid

    # After flag is set, we don't pass the key anymore, so success doesn't clear it
    error = None
    expected_api_key = None  # Key is not passed because flag is True
    tags = controller.get_tags("username")
    assert tags == returned_tags
    # Flag remains True because we didn't pass a key (urchin_api_key was None)
    assert controller.urchin_api_key_invalid


def test_overlay_controller_get_estimated_winstreaks_success() -> None:
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


def test_overlay_controller_get_estimated_winstreaks_no_api() -> None:
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


def test_overlay_controller_get_estimated_winstreaks_no_key() -> None:
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
def test_overlay_controller_get_estimated_winstreaks_error_handling(
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
