from prism.flashlight.url import FLASHLIGHT_API_URL


def test_api_url() -> None:
    # Make sure we don't release a version using the test endpoint
    assert FLASHLIGHT_API_URL == "https://flashlight.prismoverlay.com"
