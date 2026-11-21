"""
Test that all the main files can be imported
"""

import subprocess
import sys


def test_main() -> None:
    import prism.overlay.__main__  # noqa: F401


def test_testing() -> None:
    import prism.overlay.testing  # noqa: F401


def test_process_loglines() -> None:
    import prism.overlay.process_loglines  # noqa: F401


def test_run_overlay() -> None:
    import prism.overlay.output.overlay.run_overlay  # noqa: F401


def test_app_does_not_import_capture_deps() -> None:
    # The macOS build excludes these (no universal2 wheels)
    code = (
        "import sys\n"
        "import prism.overlay.__main__\n"
        "import prism.overlay.output.overlay.run_overlay\n"
        "deps = ('PIL', 'mss', 'numpy', 'scipy')\n"
        "print(sorted(m for m in deps if m in sys.modules))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"
