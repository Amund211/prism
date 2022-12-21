from PyInstaller.compat import is_darwin, is_linux, is_win

# pynput decides on runtime which modules to import
# Running this detection on GitHub Actions fails at least on Linux because it
# can't connect to an X server.

# We tell pyinstaller what modules pynput might want based on the current platform.
if is_darwin:
    hiddenimports = ["pynput.keyboard._darwin", "pynput.mouse._darwin"]
elif is_linux:
    hiddenimports = [
        "pynput.keyboard._uinput",
        "pynput.keyboard._xorg",
        "pynput.mouse._xorg",
    ]
elif is_win:
    hiddenimports = ["pynput.keyboard._win32", "pynput.mouse._win32"]
else:
    assert False, "Cannot determine environment for pynput"
