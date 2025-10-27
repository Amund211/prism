from prism.overlay.placeholder import PlaceholderWinstreakProvider
from prism.player import MISSING_WINSTREAKS


def test_placeholder_winstreak_provider() -> None:
    provider = PlaceholderWinstreakProvider()
    assert provider.seconds_until_unblocked == 0.0
    assert provider.get_estimated_winstreaks_for_uuid(
        "test-uuid", antisniper_api_key="key"
    ) == (
        MISSING_WINSTREAKS,
        False,
    )
