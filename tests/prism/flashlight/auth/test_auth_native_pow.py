import hashlib
import platform
import sys
import threading
import time
from pathlib import Path

import pytest

from prism.flashlight.auth import native_pow
from prism.flashlight.auth.native_pow import (
    IMPLEMENTATIONS,
    LIBRARY_PATH,
    MAX_COUNTER,
    NativeLibrary,
    NativePowError,
)
from prism.flashlight.auth.proof_of_work import leading_zero_bits


@pytest.fixture(scope="module")
def library() -> NativeLibrary:
    # Fail rather than skip: a missing library must never pass the native tests
    assert (
        LIBRARY_PATH.is_file()
    ), f"{LIBRARY_PATH} is missing. Build it with `uv run build_powsolve.py`."
    return NativeLibrary(LIBRARY_PATH)


@pytest.fixture(scope="module")
def supported(library: NativeLibrary) -> tuple[str, ...]:
    names = tuple(name for name in IMPLEMENTATIONS if library.supported(name))
    # The portable implementation runs everywhere
    assert "portable" in names
    return names


def is_valid(prefix: bytes, solution: str, difficulty: int) -> bool:
    digest = hashlib.sha256(prefix + solution.encode()).digest()
    return leading_zero_bits(digest) >= difficulty


def first_valid_counter(prefix: bytes, difficulty: int, start: int = 0) -> int:
    counter = start
    while not is_valid(prefix, f"{counter:012d}", difficulty):
        counter += 1
    return counter


IS_X86 = platform.machine().lower() in ("x86_64", "amd64")
IS_ARM = platform.machine().lower() in ("arm64", "aarch64")


def cpuinfo_words() -> set[str]:
    return set(Path("/proc/cpuinfo").read_text().split())


@pytest.mark.skipif(
    not (sys.platform == "linux" and IS_X86), reason="Needs /proc/cpuinfo on x86"
)
def test_sha_ni_detection_matches_cpuinfo(library: NativeLibrary) -> None:
    """Check the library's cpuid detection against the kernel's"""
    expected = {"sha_ni", "sse4_1", "ssse3"} <= cpuinfo_words()
    assert library.supported("sha-ni") == expected


@pytest.mark.skipif(
    not (sys.platform == "linux" and IS_ARM), reason="Needs /proc/cpuinfo on ARM"
)
def test_armv8_detection_matches_cpuinfo(
    library: NativeLibrary,
) -> None:
    assert library.supported("armv8") == ("sha2" in cpuinfo_words())


@pytest.mark.skipif(
    not (sys.platform == "darwin" and IS_ARM), reason="Needs Apple Silicon"
)
def test_armv8_supported_on_apple_silicon(
    library: NativeLibrary,
) -> None:
    assert library.supported("armv8")


@pytest.mark.skipif(not (IS_X86 or IS_ARM), reason="Unknown architecture")
def test_other_architectures_implementation_is_unsupported(
    library: NativeLibrary,
) -> None:
    assert not library.supported("armv8" if IS_X86 else "sha-ni")


def test_missing_library_raises(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        NativeLibrary(tmp_path / "does-not-exist")


def test_abi_version_mismatch_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_pow, "ABI_VERSION", native_pow.ABI_VERSION + 1)
    with pytest.raises(NativePowError, match="ABI version"):
        NativeLibrary(LIBRARY_PATH)


def test_unknown_implementation_is_unsupported(library: NativeLibrary) -> None:
    assert not library.supported("sha-3000")
    with pytest.raises(NativePowError, match="Unknown"):
        library.sha256("sha-3000", b"")
    with pytest.raises(NativePowError, match="Unknown"):
        library.solve("sha-3000", b"", 0)


def test_unsupported_implementation_is_refused(
    library: NativeLibrary, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An id the library does not implement, as an older library would see it
    monkeypatch.setitem(native_pow.IMPLEMENTATIONS, "future", 99)
    assert not library.supported("future")
    with pytest.raises(NativePowError, match="failed"):
        library.sha256("future", b"")
    with pytest.raises(NativePowError, match="failed"):
        library.solve("future", b"", 0)


def test_sha256_matches_hashlib(
    library: NativeLibrary, supported: tuple[str, ...]
) -> None:
    # Every length across three blocks, covering each padding boundary
    data = bytes(range(256))
    for name in supported:
        for length in range(0, 200):
            assert (
                library.sha256(name, data[:length])
                == hashlib.sha256(data[:length]).digest()
            ), (name, length)


@pytest.mark.parametrize("difficulty", (0, 1, 8))
def test_solve_returns_first_valid_counter(
    library: NativeLibrary, supported: tuple[str, ...], difficulty: int
) -> None:
    # Prefix lengths on both sides of the one/two final block boundary
    for name in supported:
        for length in range(0, 140, 3):
            prefix = b"p" * length
            solution = library.solve(name, prefix, difficulty)
            assert solution == f"{first_valid_counter(prefix, difficulty):012d}", (
                name,
                length,
            )


def test_solve_honours_start(
    library: NativeLibrary, supported: tuple[str, ...]
) -> None:
    prefix = b"a-challenge:"
    for name in supported:
        start = first_valid_counter(prefix, 8) + 1
        expected = first_valid_counter(prefix, 8, start=start)
        assert library.solve(name, prefix, 8, start=start) == f"{expected:012d}"


def test_solve_spans_chunks(
    library: NativeLibrary,
    supported: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(native_pow, "CHUNK_SIZE", 7)
    prefix = b"a-challenge:"
    expected = f"{first_valid_counter(prefix, 10):012d}"
    for name in supported:
        assert library.solve(name, prefix, 10) == expected


def test_solve_gives_up_at_the_end_of_the_range(
    library: NativeLibrary, supported: tuple[str, ...]
) -> None:
    prefix = b"a-challenge:"
    first = first_valid_counter(prefix, 8)
    for name in supported:
        # The range ends right before the first candidate that would do
        with pytest.raises(NativePowError, match="No solution"):
            library.solve(name, prefix, 8, end=first)
        assert library.solve(name, prefix, 8, end=first + 1) == f"{first:012d}"


def test_solve_rejects_bad_arguments(library: NativeLibrary) -> None:
    with pytest.raises(NativePowError, match="failed"):
        library.solve("portable", b"", 33)
    with pytest.raises(NativePowError, match="failed"):
        library.solve("portable", b"", 0, start=MAX_COUNTER, end=MAX_COUNTER + 1)


def test_solve_releases_the_gil(
    library: NativeLibrary,
    supported: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The point of the native solver: Python keeps running while it works"""
    # One foreign call for the whole range
    monkeypatch.setattr(native_pow, "CHUNK_SIZE", 1 << 22)
    durations: list[float] = []

    def work(name: str) -> None:
        start = time.perf_counter()
        try:
            library.solve(name, b"x", 32, end=1 << 21)
        except NativePowError:
            durations.append(time.perf_counter() - start)

    for name in supported:
        worker = threading.Thread(target=work, args=(name,))
        longest_pause = 0.0
        # Before start(): the worker can reach the call before start() returns
        last = time.perf_counter()
        worker.start()
        while worker.is_alive():
            now = time.perf_counter()
            longest_pause = max(longest_pause, now - last)
            last = now
        # A thread blocked for the whole call only notices once it has ended
        longest_pause = max(longest_pause, time.perf_counter() - last)
        worker.join()

        # No hash in the range has 32 leading zero bits, so it ran the whole
        # range. Holding the GIL would pause this thread for the whole call.
        assert len(durations) == 1, name
        assert longest_pause < durations.pop() / 2, name
