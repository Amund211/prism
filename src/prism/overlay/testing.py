"""Utilities for testing the overlay"""

import time
from collections.abc import Iterable

from prism.flashlight.auth.benchmark import BenchmarkSpec, parse_spec, start_benchmark
from prism.overlay.commandline import Options
from prism.ssl_errors import is_missing_local_issuer_error


def slow_iterable(
    iterable: Iterable[str], wait: float = 1
) -> Iterable[str]:  # pragma: nocover
    """Wait `wait` seconds between each yield from iterable"""
    # Used for testing
    for item in iterable:
        time.sleep(wait)
        print(f"Yielding '{item}'")
        yield item
    print("Done yielding")


def get_test_loglines(options: Options) -> Iterable[str]:  # pragma: nocover
    """Test the implementation on a static logfile or a list of loglines"""
    slow, wait = False, 1

    loglines: Iterable[str]
    if options.logfile_path is not None:
        loglines = options.logfile_path.open("r", encoding="utf8", errors="replace")
    else:
        CHAT = "(Client thread) Info [CHAT] "
        loglines = [
            "(Client thread) Info Setting user: Testing",
            f"{CHAT}You have joined [MVP++] Teammate's party!",
            f"{CHAT}You'll be partying with: Notch",
            f"{CHAT}sdflksjdfh has joined (2/16)!",
            f"{CHAT}sdflksjddfoih has joined (3/16)!",
            f"{CHAT}ONLINE: Testing, Teammate, Hypixel, Technoblade, Manhal_IQ_, SomeUnknownNick",  # noqa: E501
            # f"{CHAT}               Bed Wars ",  # game start
            # f"{CHAT}Hypixel was killed by Testing. FINAL KILL!",
            # f"{CHAT}1st Killer - [MVP+] Player1",  # game end
        ]

    if slow:
        loglines = slow_iterable(loglines, wait=wait)

    return loglines


def parse_pow_benchmark_spec(spec: str) -> BenchmarkSpec | None:  # pragma: nocover
    """
    Parse a `--test-pow` spec, printing why and returning None if it is invalid

    Separate from starting the benchmark so a typo is caught before the overlay
    starts, rather than after the logfile prompt and a window.
    """
    try:
        return parse_spec(spec)
    except ValueError as e:
        print(e)
        return None


def start_pow_benchmark(spec: BenchmarkSpec) -> None:  # pragma: nocover
    """
    Start the proof-of-work benchmark beside the overlay that is about to run

    Backgrounded on purpose: the overlay keeps starting, and the hash loop then
    competes for the GIL with the tkinter thread and the stats threads, the way
    a real login's solve does. Pass -q to keep the stats table out of the
    output.
    """
    print(
        f"Benchmarking the proof-of-work solver at difficulty "
        f"{spec.first}-{spec.last}, {spec.runs} run(s) each, beside the running "
        f"overlay. Solving fake challenges - nothing is sent to flashlight."
    )

    start_benchmark(spec, report=print)


def test_ssl() -> None:  # pragma: nocover
    """Test SSL certificate patching"""
    import requests

    try:
        resp = requests.get("https://localhost:12345")
        print("Got response:", resp.text)
    except requests.exceptions.SSLError as e:
        if is_missing_local_issuer_error(e):
            print("Caught missing local issuer SSLError:", e)
        else:
            print("Caught unknown SSLError:", e)
    except Exception as e:
        print("Caught unknown exception:", e)
