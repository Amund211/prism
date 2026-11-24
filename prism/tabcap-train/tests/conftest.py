import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    synth = parser.getgroup("synth", "synthetic tab list calibration")
    synth.addoption(
        "--synth",
        action="store_true",
        help="Run the synth calibration tests (calib.py)",
    )
    synth.addoption(
        "--synth-update",
        action="store_true",
        help="Write the current calibration metrics as the expected ones",
    )
