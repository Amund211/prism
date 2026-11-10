"""
Test that all the main files can be imported
"""


def test_main() -> None:
    import prism.overlay.__main__  # noqa: F401


def test_testing() -> None:
    import prism.overlay.testing  # noqa: F401


def test_process_loglines() -> None:
    import prism.overlay.process_loglines  # noqa: F401


def test_run_overlay() -> None:
    import prism.overlay.output.overlay.run_overlay  # noqa: F401
