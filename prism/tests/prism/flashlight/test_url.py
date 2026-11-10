from prism.flashlight.url import FLASHLIGHT_API_URL


def test_api_url() -> None:
    # Make sure we don't release a version using the test endpoint
    # NOTE: The flashlight API does **not** allow third-party access.
    #       Do not send any requests to any endpoints without explicit permission.
    #       Reach out on Discord for more information. https://discord.gg/k4FGUnEHYg
    assert FLASHLIGHT_API_URL == "https://flashlight.prismoverlay.com"
