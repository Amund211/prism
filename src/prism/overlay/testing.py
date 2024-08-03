"""Utilities for testing the overlay"""

import time
from collections.abc import Iterable

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
            f"{CHAT}Teammate has joined (2/16)!",  # out of sync
            f"{CHAT}Testing has joined (3/16)!",
            f"{CHAT}ONLINE: Testing, Teammate, Hypixel",  # in sync
            f"{CHAT}Technoblade has joined (4/16)!",
            f"{CHAT}Manhal_IQ_ has joined (5/16)!",
            f"{CHAT}edater has joined (6/16)!",  # denicked by api
            f"{CHAT}SomeUnknownNick has joined (7/16)!",  # Nicked teammate
            # f"{CHAT}               Bed Wars ",  # game start
            f"{CHAT}Hypixel was killed by Testing. FINAL KILL!",
            # f"{CHAT}1st Killer - [MVP+] Player1",  # game end
        ]

    if slow:
        loglines = slow_iterable(loglines, wait=wait)

    return loglines


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
