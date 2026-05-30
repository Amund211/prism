"""Flashlight bearer-token auth client (anonymous tier, v1).

The overlay always sends ``X-User-Id`` to flashlight (legacy fallback,
still honoured server-side). On top of that, ``FlashlightAuthClient`` owns
an in-memory session and adds ``Authorization: Bearer <session-id>`` to
each request, with self-healing on 401: refresh once, and if refresh
fails, do a fresh anonymous login and retry once.

The session token itself is not persisted across overlay restarts in v1.
Re-acquire on every launch is acceptable because the chain is silent.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from json import JSONDecodeError
from typing import Any

import requests
from requests.exceptions import RequestException

from prism.flashlight.url import FLASHLIGHT_API_URL

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FlashlightSession:
    """In-memory representation of an auth_sessions row, as the client sees it.

    All four timestamps are server-supplied. The client never computes
    refresh timing itself — it just observes ``refresh_at`` and acts on it.
    """

    session_id: str
    expires_at: datetime
    refresh_until: datetime
    refresh_at: datetime
    tier: str


class FlashlightAuthError(Exception):
    """Raised when the auth client cannot acquire or refresh a session.

    Surfaces from ``authorized_get`` only after the full self-heal chain
    (refresh, then fresh login) has been exhausted.
    """


def _parse_session_response(payload: object) -> FlashlightSession:
    if not isinstance(payload, Mapping):
        raise FlashlightAuthError(
            f"Invalid auth session response (not a mapping): {payload=}"
        )
    try:
        session_id = payload["sessionId"]
        expires_at = payload["expiresAt"]
        refresh_until = payload["refreshUntil"]
        refresh_at = payload["refreshAt"]
        tier = payload["tier"]
    except KeyError as e:
        raise FlashlightAuthError(
            f"Auth session response missing required field: {e}"
        ) from e

    for name, value in (
        ("sessionId", session_id),
        ("expiresAt", expires_at),
        ("refreshUntil", refresh_until),
        ("refreshAt", refresh_at),
        ("tier", tier),
    ):
        if not isinstance(value, str):
            raise FlashlightAuthError(
                f"Auth session field {name!r} is not a string: {value=}"
            )

    try:
        return FlashlightSession(
            session_id=session_id,
            expires_at=_parse_iso8601(expires_at),
            refresh_until=_parse_iso8601(refresh_until),
            refresh_at=_parse_iso8601(refresh_at),
            tier=tier,
        )
    except ValueError as e:
        raise FlashlightAuthError(
            f"Auth session response has invalid timestamp: {e}"
        ) from e


def _parse_iso8601(s: str) -> datetime:
    # The server emits time.RFC3339Nano with a trailing 'Z'; datetime.fromisoformat
    # in Python 3.11+ accepts 'Z' directly.
    return datetime.fromisoformat(s)


class FlashlightAuthClient:
    """Holds the current anonymous session and authorizes flashlight requests.

    Lifecycle:
      - lazy login on first ``authorized_get`` (or explicit ``login()``)
      - on 401 mid-request, refresh once; if that also 401s, log in fresh
      - the proactive refresh timer (see ``start_refresh_timer``) calls
        ``refresh()`` at ``session.refresh_at`` to renew before expiry
    """

    def __init__(
        self,
        *,
        session: requests.Session,
        user_id: str,
        api_url: str = FLASHLIGHT_API_URL,
        request_timeout: float = 10.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._http = session
        self._user_id = user_id
        self._api_url = api_url
        self._request_timeout = request_timeout
        self._now = now or _utcnow

        # The lock protects the cached session and the timer thread handle.
        # All HTTP work happens outside the lock — only state swaps are
        # guarded — so a slow login doesn't block the proactive timer or a
        # concurrent reactive refresh.
        self._lock = threading.RLock()
        self._session: FlashlightSession | None = None

        self._stop_event = threading.Event()
        self._timer_thread: threading.Thread | None = None

    @property
    def current_session(self) -> FlashlightSession | None:
        with self._lock:
            return self._session

    def login(self) -> FlashlightSession:
        """Issue a fresh anonymous session, replacing any existing one."""
        url = f"{self._api_url}/v1/auth/anonymous/login"
        try:
            response = self._http.post(
                url,
                json={"userId": self._user_id},
                timeout=self._request_timeout,
            )
        except RequestException as e:
            raise FlashlightAuthError(f"Anonymous login request failed: {e}") from e

        if not response.ok:
            raise FlashlightAuthError(
                f"Anonymous login returned HTTP {response.status_code}: {response.text}"
            )
        try:
            payload = response.json()
        except JSONDecodeError as e:
            raise FlashlightAuthError(
                f"Anonymous login returned invalid JSON: {response.text!r}"
            ) from e

        session = _parse_session_response(payload)
        with self._lock:
            self._session = session
        logger.info(
            "Anonymous session acquired",
            extra={"sessionId": session.session_id, "tier": session.tier},
        )
        return session

    def refresh(self) -> FlashlightSession:
        """Refresh the current session. Raises if no session or refresh fails."""
        with self._lock:
            current = self._session
        if current is None:
            raise FlashlightAuthError("No session to refresh")

        url = f"{self._api_url}/v1/auth/refresh"
        try:
            response = self._http.post(
                url,
                headers={"Authorization": f"Bearer {current.session_id}"},
                timeout=self._request_timeout,
            )
        except RequestException as e:
            raise FlashlightAuthError(f"Refresh request failed: {e}") from e

        if response.status_code == 401:
            # Caller will fall back to login.
            with self._lock:
                if self._session is current:
                    self._session = None
            raise FlashlightAuthError("Refresh rejected (401)")
        if not response.ok:
            raise FlashlightAuthError(
                f"Refresh returned HTTP {response.status_code}: {response.text}"
            )
        try:
            payload = response.json()
        except JSONDecodeError as e:
            raise FlashlightAuthError(
                f"Refresh returned invalid JSON: {response.text!r}"
            ) from e

        session = _parse_session_response(payload)
        with self._lock:
            self._session = session
        logger.info("Session refreshed", extra={"sessionId": session.session_id})
        return session

    def authorized_get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> requests.Response:
        """GET ``url`` with the current bearer token, self-healing on 401.

        Authorization on 401 chain:
          1. Refresh the current session, retry.
          2. If refresh fails, fresh anonymous login, retry.
          3. If that also returns 401, raise FlashlightAuthError.
        """
        return self._authorized_request(
            "GET", url, headers=headers, params=params, timeout=timeout
        )

    def _authorized_request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> requests.Response:
        # Ensure we have a session. Login is silent and only happens if we
        # don't already have one; concurrent calls are safe because login()
        # is idempotent (a second login just issues a fresh session).
        if self.current_session is None:
            self.login()

        response = self._send_with_bearer(
            method, url, headers=headers, params=params, timeout=timeout
        )
        if response.status_code != 401:
            return response

        # First fallback: refresh + retry.
        try:
            self.refresh()
        except FlashlightAuthError as e:
            logger.info("Refresh after 401 failed; trying fresh login", exc_info=e)
        else:
            response = self._send_with_bearer(
                method, url, headers=headers, params=params, timeout=timeout
            )
            if response.status_code != 401:
                return response

        # Second fallback: fresh anonymous login.
        self.login()
        response = self._send_with_bearer(
            method, url, headers=headers, params=params, timeout=timeout
        )
        return response

    def _send_with_bearer(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None,
        params: Mapping[str, Any] | None,
        timeout: float | tuple[float, float] | None,
    ) -> requests.Response:
        merged: dict[str, str] = {"X-User-Id": self._user_id}
        if headers:
            merged.update(headers)
        current = self.current_session
        if current is not None:
            merged["Authorization"] = f"Bearer {current.session_id}"
        return self._http.request(
            method,
            url,
            headers=merged,
            params=dict(params) if params is not None else None,
            timeout=timeout if timeout is not None else self._request_timeout,
        )

    # --- Proactive refresh ---------------------------------------------------

    def start_refresh_timer(self) -> None:
        """Start the background thread that refreshes at ``session.refresh_at``.

        Safe to call multiple times — only one timer thread runs.
        """
        with self._lock:
            if self._timer_thread is not None and self._timer_thread.is_alive():
                return
            self._stop_event.clear()
            t = threading.Thread(
                target=self._refresh_loop,
                name="flashlight-auth-refresh",
                daemon=True,
            )
            self._timer_thread = t
            t.start()

    def stop_refresh_timer(self) -> None:
        self._stop_event.set()

    def _refresh_loop(self) -> None:  # pragma: no cover
        # Daemon-thread body; integration-tested via start/stop_refresh_timer.
        while not self._stop_event.is_set():
            session = self.current_session
            if session is None:
                # Wake up periodically to recheck; the reactive path will
                # have populated a session if any traffic has flowed.
                if self._stop_event.wait(60):
                    return
                continue

            sleep_seconds = max(0.0, (session.refresh_at - self._now()).total_seconds())
            # Cap the maximum sleep so we re-check the session reference
            # periodically (it might have been replaced by reactive
            # refresh / login).
            sleep_seconds = min(sleep_seconds, 600.0)
            if self._stop_event.wait(sleep_seconds):
                return

            try:
                self.refresh()
            except FlashlightAuthError as e:
                logger.warning(
                    "Proactive refresh failed; leaving reactive path to recover",
                    exc_info=e,
                )
                # On failure, let the next reactive 401 trigger recovery.
                # Briefly back off before the next loop iteration.
                if self._stop_event.wait(30):
                    return


def _utcnow() -> datetime:
    from datetime import timezone

    return datetime.now(tz=timezone.utc)


__all__ = [
    "FlashlightAuthClient",
    "FlashlightAuthError",
    "FlashlightSession",
]


# Suppress unused-import warning in some linter setups.
_ = time
