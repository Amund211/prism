from prism.player import MISSING_WINSTREAKS
from prism.requests import make_prism_requests_session
from prism.strange import STATS_ENDPOINT, StrangePlayerProvider
from tests.prism.overlay.utils import make_winstreaks

assert MISSING_WINSTREAKS == make_winstreaks()


def test_stats_endpoint() -> None:
    # Make sure we don't release a version using the test endpoint
    assert STATS_ENDPOINT == "https://flashlight.prismoverlay.com/v1/playerdata"


def test_strange_player_provider() -> None:
    provider = StrangePlayerProvider(
        retry_limit=3,
        initial_timeout=1.0,
        get_time_ns=lambda: 1234567890123456789,
        session=make_prism_requests_session(),
    )
    assert provider.seconds_until_unblocked == 0.0
