from collections.abc import Iterator

import pytest
import requests

from prism.flashlight.auth import loopback
from prism.flashlight.auth.preview import PreviewServer


@pytest.fixture(autouse=True)
def fast_close(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loopback, "POLL_INTERVAL_SECONDS", 0.01)


@pytest.fixture
def http() -> Iterator[requests.Session]:
    with requests.Session() as session:
        session.trust_env = False
        yield session


@pytest.fixture
def server() -> Iterator[PreviewServer]:
    with PreviewServer() as server:
        yield server


def test_lists_every_page(server: PreviewServer) -> None:
    labels = [state.label for state in server.states]

    assert labels[0] == "Success"
    assert "Error: no_game, no_profile" in labels
    assert "Error: unknown code" in labels
    assert "404 Not found" in labels
    assert "400 Bad request" in labels
    # One entry per distinct message
    assert len([label for label in labels if "flow_expired" in label]) == 1


def test_states_are_the_real_pages(
    http: requests.Session, server: PreviewServer
) -> None:
    for state in server.states:
        response = http.get(state.url, timeout=5)
        assert response.status_code == state.status, state.label

    success = http.get(server.states[0].url, timeout=5)
    assert "<h1>Return to Prism</h1>" in success.text


def test_serves_the_panel(http: requests.Session, server: PreviewServer) -> None:
    response = http.get(server.url, timeout=5)

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert "<iframe" in response.text
    for state in server.states:
        assert state.url in response.text


def test_panel_is_only_at_the_root(
    http: requests.Session, server: PreviewServer
) -> None:
    assert http.get(f"{server.url}nope", timeout=5).status_code == 404
