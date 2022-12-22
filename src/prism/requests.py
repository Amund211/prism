import requests

from prism import USER_AGENT


def make_prism_requests_session() -> requests.Session:
    """Create a requests session object for making http requests"""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session
