"""
Test that all the main files can be imported
"""


def test_main() -> None:
    import prism.overlay.__main__  # noqa: F401


def test_get_api_key() -> None:
    import prism.overlay.user_interaction.get_api_key  # noqa: F401
