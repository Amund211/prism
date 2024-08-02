# isort: skip_file
"""
Test that all the main files can be imported
"""


def test_main() -> None:
    import prism.overlay.__main__  # noqa: F401


def test_testing() -> None:
    import prism.overlay.testing  # noqa: F401


def test_use_system_certs() -> None:
    # Import use_system_certs first to enable patching
    import prism.use_system_certs  # noqa: F401

    # Import requests as well to make sure the patching works
    # NOTE: Requests is likely imported already by this point, so the patching
    # will likely not get tested here
    import requests  # noqa: F401
