from prism.player import MISSING_WINSTREAKS
from prism.requests import make_prism_requests_session
from prism.strange import STATS_ENDPOINT, StrangePlayerProvider
from tests.prism.overlay.utils import make_winstreaks

assert MISSING_WINSTREAKS == make_winstreaks()


def test_stats_endpoint() -> None:
    # Make sure we're using the correct endpoint on release
    # NOTE: The flashlight API does **not** allow third-party access.
    #       Do not send any requests to any endpoints without explicit permission.
    #       Reach out on Discord for more information. https://discord.gg/k4FGUnEHYg
    assert STATS_ENDPOINT == "https://flashlight.prismoverlay.com/v1/playerdata"


def test_strange_player_provider() -> None:
    provider = StrangePlayerProvider(
        retry_limit=3,
        initial_timeout=1.0,
        get_time_ns=lambda: 1234567890123456789,
        session=make_prism_requests_session(),
    )
    assert provider.seconds_until_unblocked == 0.0
