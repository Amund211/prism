from pathlib import Path

from PyInstaller.utils.hooks import get_module_file_attribute

from prism.flashlight.auth.native_pow import LIBRARY_NAME

# The native solver is loaded with ctypes, so pyinstaller can't find it itself.
# A missing library fails the build: the overlay would still run, but on the
# much slower Python solver.
module_file = get_module_file_attribute("prism.flashlight.auth.native_pow")
assert module_file is not None
library = Path(module_file).with_name(LIBRARY_NAME)

if not library.is_file():
    raise SystemExit(
        f"{library} is missing. Run `uv run build_powsolve.py` before pyinstaller."
    )

binaries = [(str(library), "prism/flashlight/auth")]
