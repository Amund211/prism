"""Tests for the flashlight bearer-token auth client.

Uses a fake ``requests.Session`` adapter so we exercise the real HTTP call
path through ``self._http.request(...)`` without hitting the network.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import pytest
import requests
from requests.adapters import BaseAdapter
from requests.models import PreparedRequest

from prism.flashlight.auth import (
    FlashlightAuthClient,
    FlashlightAuthError,
    FlashlightSession,
)


class FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None) -> None:
        self.status_code = status_code
        self._body = body
        self.ok = 200 <= status_code < 300
        self.text = repr(body)

    def json(self) -> dict[str, Any]:
        if self._body is None:
            raise ValueError("no body")
        return self._body


class FakeAdapter(BaseAdapter):
    """A ``requests``-compatible adapter that returns scripted responses.

    Each call to ``send`` pops a response from the scripted queue. Recorded
    requests are appended to ``calls`` so tests can assert on URL, method
    and headers.
    """

    def __init__(
        self,
        responses: Iterator[FakeResponse | Callable[[PreparedRequest], FakeResponse]],
    ) -> None:
        super().__init__()
        self.responses = responses
        self.calls: list[PreparedRequest] = []

    def send(  # type: ignore[override]
        self,
        request: PreparedRequest,
        **kwargs: Any,
    ) -> requests.Response:
        self.calls.append(request)
        try:
            scripted = next(self.responses)
        except StopIteration:
            raise AssertionError(
                f"No scripted response for request {request.method} {request.url}"
            )
        if callable(scripted):
            scripted = scripted(request)
        response = requests.Response()
        response.status_code = scripted.status_code
        body = scripted._body
        if body is None:
            response._content = b""
        else:
            import json

            response._content = json.dumps(body).encode("utf-8")
        response.url = request.url or ""
        response.request = request
        return response

    def close(self) -> None:
        pass


def make_session_payload(
    session_id: str = "sess-1",
    *,
    tier: str = "anonymous",
    now: datetime | None = None,
    ttl_minutes: int = 60,
) -> dict[str, Any]:
    now = now or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "sessionId": session_id,
        "expiresAt": (now + timedelta(minutes=ttl_minutes)).isoformat(),
        "refreshUntil": (now + timedelta(minutes=ttl_minutes * 2)).isoformat(),
        "refreshAt": (now + timedelta(minutes=ttl_minutes - 5)).isoformat(),
        "tier": tier,
    }


def make_client_with_adapter(
    responses: list[FakeResponse | Callable[[PreparedRequest], FakeResponse]],
    *,
    user_id: str = "user-abc",
    api_url: str = "http://flashlight.test",
) -> tuple[FlashlightAuthClient, FakeAdapter]:
    session = requests.Session()
    adapter = FakeAdapter(iter(responses))
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    client = FlashlightAuthClient(
        session=session,
        user_id=user_id,
        api_url=api_url,
        request_timeout=1.0,
    )
    return client, adapter


def test_login_stores_session_and_returns_view() -> None:
    payload = make_session_payload(session_id="sid-A")
    client, _ = make_client_with_adapter([FakeResponse(200, payload)])

    session = client.login()

    assert isinstance(session, FlashlightSession)
    assert session.session_id == "sid-A"
    assert session.tier == "anonymous"
    assert client.current_session is session


def test_login_failure_raises_auth_error() -> None:
    client, _ = make_client_with_adapter([FakeResponse(500, {"detail": "boom"})])
    with pytest.raises(FlashlightAuthError):
        client.login()
    assert client.current_session is None


def test_authorized_get_lazy_logs_in_then_calls_endpoint() -> None:
    """First authorized call should login then hit the target URL."""
    payload = make_session_payload(session_id="sid-1")
    client, adapter = make_client_with_adapter(
        [
            FakeResponse(200, payload),  # login
            FakeResponse(200, {"hello": "world"}),  # target
        ]
    )
    r = client.authorized_get("http://flashlight.test/v1/playerdata")
    assert r.status_code == 200
    # 2 requests in order: login then target.
    assert len(adapter.calls) == 2
    assert urlparse(adapter.calls[0].url or "").path == "/v1/auth/anonymous/login"
    assert adapter.calls[1].headers.get("Authorization") == "Bearer sid-1"
    assert adapter.calls[1].headers.get("X-User-Id") == "user-abc"


def test_authorized_get_sends_bearer_when_session_exists() -> None:
    payload = make_session_payload(session_id="sid-1")
    client, adapter = make_client_with_adapter(
        [
            FakeResponse(200, payload),
            FakeResponse(200, {}),
        ]
    )
    client.login()
    r = client.authorized_get("http://flashlight.test/v1/tags/abc")
    assert r.status_code == 200
    assert adapter.calls[1].headers.get("Authorization") == "Bearer sid-1"


def test_401_triggers_refresh_then_retry() -> None:
    initial = make_session_payload(session_id="sid-1")
    refreshed = make_session_payload(session_id="sid-2")
    client, adapter = make_client_with_adapter(
        [
            FakeResponse(200, initial),  # initial login
            FakeResponse(401, {"detail": "expired"}),  # first attempt 401s
            FakeResponse(200, refreshed),  # refresh succeeds
            FakeResponse(200, {"ok": True}),  # retry succeeds
        ]
    )
    client.login()
    r = client.authorized_get("http://flashlight.test/v1/playerdata")
    assert r.status_code == 200
    assert len(adapter.calls) == 4
    assert urlparse(adapter.calls[2].url or "").path == "/v1/auth/refresh"
    assert adapter.calls[3].headers.get("Authorization") == "Bearer sid-2"


def test_401_after_refresh_failure_falls_back_to_login() -> None:
    initial = make_session_payload(session_id="sid-1")
    fresh = make_session_payload(session_id="sid-3")
    client, adapter = make_client_with_adapter(
        [
            FakeResponse(200, initial),  # initial login
            FakeResponse(401, {"detail": "expired"}),  # first attempt 401s
            FakeResponse(401, {"detail": "rejected"}),  # refresh 401s
            FakeResponse(200, fresh),  # fresh login
            FakeResponse(200, {"ok": True}),  # retry succeeds
        ]
    )
    client.login()
    r = client.authorized_get("http://flashlight.test/v1/playerdata")
    assert r.status_code == 200
    paths = [urlparse(c.url or "").path for c in adapter.calls]
    assert paths == [
        "/v1/auth/anonymous/login",
        "/v1/playerdata",
        "/v1/auth/refresh",
        "/v1/auth/anonymous/login",
        "/v1/playerdata",
    ]
    assert client.current_session is not None
    assert client.current_session.session_id == "sid-3"


def test_authorized_get_merges_caller_headers() -> None:
    payload = make_session_payload()
    client, adapter = make_client_with_adapter(
        [
            FakeResponse(200, payload),
            FakeResponse(200, {}),
        ]
    )
    client.login()
    client.authorized_get(
        "http://flashlight.test/v1/tags/uuid",
        headers={"X-Urchin-Api-Key": "secret"},
    )
    headers = adapter.calls[1].headers
    assert headers.get("X-Urchin-Api-Key") == "secret"
    auth_header = headers.get("Authorization", "")
    assert isinstance(auth_header, str) and auth_header.startswith("Bearer ")
    assert headers.get("X-User-Id") == "user-abc"


def test_refresh_without_session_raises() -> None:
    client, _ = make_client_with_adapter([])
    with pytest.raises(FlashlightAuthError):
        client.refresh()


def test_refresh_401_clears_session_and_raises() -> None:
    payload = make_session_payload()
    client, _ = make_client_with_adapter(
        [
            FakeResponse(200, payload),
            FakeResponse(401, {"detail": "no"}),
        ]
    )
    client.login()
    assert client.current_session is not None
    with pytest.raises(FlashlightAuthError):
        client.refresh()
    assert client.current_session is None


def test_login_rejects_malformed_payload() -> None:
    client, _ = make_client_with_adapter([FakeResponse(200, {"unexpected": "shape"})])
    with pytest.raises(FlashlightAuthError):
        client.login()


def test_login_rejects_invalid_timestamp() -> None:
    bad = make_session_payload()
    bad["expiresAt"] = "not-a-date"
    client, _ = make_client_with_adapter([FakeResponse(200, bad)])
    with pytest.raises(FlashlightAuthError):
        client.login()


def test_refresh_timer_starts_and_stops_cleanly() -> None:
    payload = make_session_payload()
    client, _ = make_client_with_adapter([FakeResponse(200, payload)])
    client.login()
    client.start_refresh_timer()
    # Idempotent: second call is a no-op
    client.start_refresh_timer()
    client.stop_refresh_timer()
    # Cooperative shutdown — give the thread a chance to exit.
    timer = client._timer_thread
    assert timer is not None
    timer.join(timeout=2)
    assert not timer.is_alive()


def test_authorized_get_propagates_non_401_errors() -> None:
    payload = make_session_payload()
    client, adapter = make_client_with_adapter(
        [
            FakeResponse(200, payload),
            FakeResponse(500, {"detail": "server boom"}),
        ]
    )
    client.login()
    r = client.authorized_get("http://flashlight.test/v1/playerdata")
    assert r.status_code == 500
    # No refresh attempted on non-401.
    assert len(adapter.calls) == 2


def test_parse_rejects_non_mapping_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-dict but valid-JSON body (server bug or proxy mishap) is rejected."""
    payload = make_session_payload()
    client, _ = make_client_with_adapter([FakeResponse(200, payload)])

    def fake_post(*args: object, **kwargs: object) -> requests.Response:
        response = requests.Response()
        response.status_code = 200
        response._content = b'["not", "a", "mapping"]'
        response.url = "http://flashlight.test/v1/auth/anonymous/login"
        return response

    monkeypatch.setattr(client._http, "post", fake_post)
    with pytest.raises(FlashlightAuthError):
        client.login()


def test_parse_rejects_non_string_field() -> None:
    """A field of unexpected type doesn't pass through to FlashlightSession."""
    payload = make_session_payload()
    payload["sessionId"] = 12345
    client, _ = make_client_with_adapter([FakeResponse(200, payload)])
    with pytest.raises(FlashlightAuthError):
        client.login()


def test_login_translates_network_errors() -> None:
    """A RequestException from the transport bubbles up as FlashlightAuthError."""

    def raise_network(_: PreparedRequest) -> FakeResponse:
        raise requests.exceptions.ConnectionError("no network")

    client, _ = make_client_with_adapter([raise_network])
    with pytest.raises(FlashlightAuthError):
        client.login()


def test_refresh_translates_network_errors() -> None:
    payload = make_session_payload()

    def raise_network(_: PreparedRequest) -> FakeResponse:
        raise requests.exceptions.ConnectionError("no network")

    client, _ = make_client_with_adapter([FakeResponse(200, payload), raise_network])
    client.login()
    with pytest.raises(FlashlightAuthError):
        client.refresh()


def test_refresh_translates_non_ok_status() -> None:
    """500-class responses from refresh raise rather than silently returning."""
    payload = make_session_payload()
    client, _ = make_client_with_adapter(
        [FakeResponse(200, payload), FakeResponse(503, {"detail": "down"})]
    )
    client.login()
    with pytest.raises(FlashlightAuthError):
        client.refresh()
    # 503 (vs 401) should not clear the cached session.
    assert client.current_session is not None


def test_login_translates_invalid_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-JSON 2xx body is reported as FlashlightAuthError."""
    payload = make_session_payload()
    client, _ = make_client_with_adapter([FakeResponse(200, payload)])

    # Patch the transport so the response has a 200 status but a body that
    # is not valid JSON. Easiest to do with monkeypatched http.post.
    real_post = client._http.post

    def fake_post(*args: object, **kwargs: object) -> requests.Response:
        response = requests.Response()
        response.status_code = 200
        response._content = b"not valid json {"
        response.url = "http://flashlight.test/v1/auth/anonymous/login"
        return response

    monkeypatch.setattr(client._http, "post", fake_post)
    with pytest.raises(FlashlightAuthError):
        client.login()
    # Re-bind to silence unused-name warnings on `real_post`.
    _ = real_post


def test_refresh_translates_invalid_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = make_session_payload()
    client, _ = make_client_with_adapter([FakeResponse(200, payload)])
    client.login()

    def fake_post(*args: object, **kwargs: object) -> requests.Response:
        response = requests.Response()
        response.status_code = 200
        response._content = b"not valid json {"
        response.url = "http://flashlight.test/v1/auth/refresh"
        return response

    monkeypatch.setattr(client._http, "post", fake_post)
    with pytest.raises(FlashlightAuthError):
        client.refresh()


# Suppress unused-import warning for `threading`, exposed for symmetry with
# the auth module under test.
_ = threading
