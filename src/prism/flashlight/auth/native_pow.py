"""
Load the native proof-of-work solver built from powsolve.c

ctypes releases the GIL for the whole of every foreign call, so the solve runs
in parallel with the UI rather than taking turns with it on the interpreter.
Build the library with `uv run build_powsolve.py`.
"""

import ctypes
import sys
from pathlib import Path

SOURCE_PATH = Path(__file__).with_name("powsolve.c")

if sys.platform == "win32":  # pragma: nocover
    LIBRARY_NAME = "_powsolve.dll"
elif sys.platform == "darwin":  # pragma: nocover
    LIBRARY_NAME = "_powsolve.dylib"
else:  # pragma: nocover
    LIBRARY_NAME = "_powsolve.so"

LIBRARY_PATH = SOURCE_PATH.with_name(LIBRARY_NAME)

# Must match ABI_VERSION, SOLUTION_DIGITS and MAX_COUNTER in powsolve.c
ABI_VERSION = 1
SOLUTION_DIGITS = 12
MAX_COUNTER = 10**SOLUTION_DIGITS

# Implementation ids in powsolve.c, by name
IMPLEMENTATIONS = {"portable": 1}

# Counters per foreign call. Small enough that a call never runs for long, so
# the thread comes back to Python regularly.
CHUNK_SIZE = 1 << 20


class NativePowError(Exception):
    """The native solver failed or can't be used"""


class NativeLibrary:
    """The native solver library, loaded from `path`"""

    def __init__(self, path: Path) -> None:
        """Load the library. Raises OSError or NativePowError."""
        # CDLL, not PyDLL: CDLL is what releases the GIL during calls
        self._lib = lib = ctypes.CDLL(str(path))

        lib.pow_abi_version.argtypes = []
        lib.pow_abi_version.restype = ctypes.c_int
        abi_version = lib.pow_abi_version()
        if abi_version != ABI_VERSION:
            raise NativePowError(
                f"{path} has ABI version {abi_version}, expected {ABI_VERSION}"
            )

        lib.pow_impl_supported.argtypes = [ctypes.c_int]
        lib.pow_impl_supported.restype = ctypes.c_int

        lib.pow_sha256.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_char_p,
        ]
        lib.pow_sha256.restype = ctypes.c_int

        lib.pow_solve.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_uint64,
            ctypes.POINTER(ctypes.c_uint64),
        ]
        lib.pow_solve.restype = ctypes.c_int

    def supported(self, name: str) -> bool:
        """Return True if the named implementation can run on this machine"""
        impl = IMPLEMENTATIONS.get(name, None)
        return impl is not None and bool(self._lib.pow_impl_supported(impl))

    def sha256(self, name: str, data: bytes) -> bytes:
        """Return SHA-256 of `data` computed by the named implementation"""
        out = ctypes.create_string_buffer(32)
        if self._lib.pow_sha256(_impl_id(name), data, len(data), out) != 0:
            raise NativePowError(f"pow_sha256 failed with implementation {name}")
        return out.raw

    def solve(
        self,
        name: str,
        prefix: bytes,
        difficulty: int,
        *,
        start: int = 0,
        end: int = MAX_COUNTER,
    ) -> str:
        """
        Return the first solution in counters [start, end)

        Raises NativePowError if there is none, or on bad arguments.
        """
        impl = _impl_id(name)
        found = ctypes.c_uint64()
        for chunk_start in range(start, end, CHUNK_SIZE):
            chunk_end = min(chunk_start + CHUNK_SIZE, end)
            result = self._lib.pow_solve(
                impl,
                prefix,
                len(prefix),
                difficulty,
                chunk_start,
                chunk_end,
                ctypes.byref(found),
            )
            if result == 1:
                return f"{found.value:0{SOLUTION_DIGITS}d}"
            if result != 0:
                raise NativePowError(
                    f"pow_solve failed with implementation {name}, "
                    f"{difficulty=}, {chunk_start=}, {chunk_end=}"
                )
        raise NativePowError(f"No solution in counters [{start}, {end})")


def _impl_id(name: str) -> int:
    impl = IMPLEMENTATIONS.get(name, None)
    if impl is None:
        raise NativePowError(f"Unknown native implementation {name!r}")
    return impl
