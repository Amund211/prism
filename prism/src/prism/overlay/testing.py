"""Utilities for testing the overlay"""

import time
from collections.abc import Iterable
from pathlib import Path

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


def test_pow(solver_name: str) -> None:  # pragma: nocover
    """Solve and verify challenges with the named proof-of-work solver"""
    from prism.flashlight.auth.proof_of_work import default_solver, self_test

    print(f"Default proof-of-work solver: {default_solver().name}")
    solver = self_test(solver_name)
    # Only printed if every solution verified. Raises otherwise.
    print(f"Proof-of-work OK: {solver.name}")


def test_tabcap(path: Path) -> None:  # pragma: nocover
    """Read the tab list in a screenshot. Checks that the reader runs in the build"""
    import numpy as np
    from PIL import Image

    from prism.overlay.tabcap.reader import read_tab

    with Image.open(path) as image:
        rows = read_tab(np.asarray(image.convert("RGB")))
    teams = sum(team is not None for _, team in rows)
    # Names are not printed: real screenshots have real names
    if not teams:
        raise SystemExit(f"Tabcap failed: {len(rows)} rows, no team read")
    print(f"Tabcap OK: {len(rows)} rows, {teams} teams")


def preview_signin_page() -> None:  # pragma: nocover
    """Serve every state of the sign-in page with a control panel until ctrl+c"""
    import time
    import webbrowser

    from prism.flashlight.auth.preview import PreviewServer

    with PreviewServer() as server:
        print(f"Sign-in page preview at {server.url} - ctrl+c to stop")
        webbrowser.open(server.url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


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
