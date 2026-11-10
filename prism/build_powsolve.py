"""
Build the native proof-of-work solver next to its loader

Run with `uv run build_powsolve.py` before running the tests or pyinstaller.
Uses clang on every platform, or the compiler in $CC.
"""

import os
import subprocess
import sys
import sysconfig

from prism.flashlight.auth.native_pow import LIBRARY_PATH, SOURCE_PATH


def compile_command() -> list[str]:
    """Return the compiler invocation for this platform"""
    command = [
        os.environ.get("CC", "clang"),
        "-O3",
        # About +10% for every implementation
        "-funroll-loops",
        "-shared",
        "-Wall",
        "-Werror",
        "-o",
        str(LIBRARY_PATH),
        str(SOURCE_PATH),
    ]

    if sys.platform == "darwin":
        # pyinstaller builds a universal2 app, so the library needs both slices
        command += ["-arch", "x86_64", "-arch", "arm64"]
        target = sysconfig.get_config_var("MACOSX_DEPLOYMENT_TARGET")
        if target:
            command.append(f"-mmacosx-version-min={target}")
    elif sys.platform != "win32":
        command += ["-fPIC", "-fvisibility=hidden"]

    return command


def main() -> None:
    command = compile_command()
    print(" ".join(command), file=sys.stderr)
    subprocess.run(command, check=True)
    print(f"Built {LIBRARY_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
