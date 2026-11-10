import requests
import requests.adapters

from prism import USER_AGENT


def make_prism_requests_session() -> requests.Session:
    """Create a requests session object for making http requests"""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # Mount adapters with space for 16 connections, as we run with 16 threads by default
    # Using the default of 10, the 11th-16th active connections at any time will
    # be discarded after use.
    for prefix in ("https://", "http://"):
        adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16)
        session.mount(prefix, adapter)

    return session
