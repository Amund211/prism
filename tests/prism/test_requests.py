import requests

from prism import USER_AGENT
from prism.requests import make_prism_requests_session


def test_make_prism_requests_session() -> None:
    session = make_prism_requests_session()
    assert isinstance(session, requests.Session)
    assert session.headers["User-Agent"] == USER_AGENT
