"""Flashlight bearer-token auth client (anonymous tier, v1).

The overlay always sends ``X-User-Id`` to flashlight (legacy fallback,
still honoured server-side). On top of that, ``FlashlightAuthClient`` owns
an in-memory session and adds ``Authorization: Bearer <session-id>`` to
each request, with self-healing on 401: refresh once, and if refresh
fails, do a fresh anonymous login and retry once.

The session token itself is not persisted across overlay restarts in v1.
Re-acquire on every launch is acceptable because the chain is silent.

Design note — no wall-clock reads. Every timing decision is driven by a
monotonic deadline computed from the server-supplied duration at the
moment the response arrives. The client never compares timestamps
against ``datetime.now()``: a frozen laptop, NTP skew, or DST roll-over
cannot cause spurious refreshes. The contract on the wire is pure
seconds-from-now.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any

import requests
from requests.exceptions import RequestException

from prism.flashlight.url import FLASHLIGHT_API_URL

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FlashlightSession:
    """In-memory representation of an auth_sessions row, as the client sees it.

    ``refresh_at_monotonic`` is a monotonic-clock deadline (in seconds,
    same scale as :func:`time.monotonic`) computed from the
    server-supplied ``refreshInSeconds`` at the moment the response
    landed. The proactive timer compares it only against
    :func:`time.monotonic`, never against wall-clock time.

    ``can_refresh`` is the server's "should I bother calling /refresh?"
    hint: ``True`` while another refresh would still grant a full
    window, ``False`` on the final refresh whose ``refresh_until`` got
    pinned to the absolute lifetime cap. When the timer fires with
    ``can_refresh=False`` the client does a full re-login instead of
    calling /refresh.
    """

    session_id: str
    tier: str
    can_refresh: bool
    refresh_at_monotonic: float


class FlashlightAuthError(Exception):
    """Raised when the auth client cannot acquire or refresh a session.

    Surfaces from ``authorized_get`` only after the full self-heal chain
    (refresh, then fresh login) has been exhausted.
    """


def _parse_session_response(payload: object, monotonic_now: float) -> FlashlightSession:
    if not isinstance(payload, Mapping):
        raise FlashlightAuthError(
            f"Invalid auth session response (not a mapping): {payload=}"
        )
    try:
        session_id = payload["sessionId"]
        tier = payload["tier"]
        refresh_in_seconds = payload["refreshInSeconds"]
        can_refresh = payload["canRefresh"]
    except KeyError as e:
        raise FlashlightAuthError(
            f"Auth session response missing required field: {e}"
        ) from e

    if not isinstance(session_id, str):
        raise FlashlightAuthError(
            f"Auth session field 'sessionId' is not a string: {session_id=}"
        )
    if not isinstance(tier, str):
        raise FlashlightAuthError(f"Auth session field 'tier' is not a string: {tier=}")
    if not isinstance(can_refresh, bool):
        raise FlashlightAuthError(
            f"Auth session field 'canRefresh' is not a bool: {can_refresh=}"
        )
    # Accept ints; reject bools (which are also ints in Python) and floats.
    if isinstance(refresh_in_seconds, bool) or not isinstance(refresh_in_seconds, int):
        raise FlashlightAuthError(
            "Auth session field 'refreshInSeconds' is not an int: "
            f"{refresh_in_seconds=}"
        )
    if refresh_in_seconds < 0:
        raise FlashlightAuthError(
            f"Auth session field 'refreshInSeconds' is negative: {refresh_in_seconds=}"
        )

    return FlashlightSession(
        session_id=session_id,
        tier=tier,
        can_refresh=can_refresh,
        refresh_at_monotonic=monotonic_now + float(refresh_in_seconds),
    )


class FlashlightAuthClient:
    """Holds the current anonymous session and authorizes flashlight requests.

    Lifecycle:
      - lazy login on first ``authorized_get`` (or explicit ``login()``)
      - on 401 mid-request, refresh once; if that also 401s, log in fresh
      - the proactive refresh timer (see ``start_refresh_timer``) wakes
        up at the session's ``refresh_at_monotonic`` deadline and either
        calls ``refresh()`` (when ``can_refresh`` is True) or
        ``login()`` (when False, i.e. the server has signalled that the
        next refresh would be useless).
    """

    def __init__(
        self,
        *,
        session: requests.Session,
        user_id: str,
        api_url: str = FLASHLIGHT_API_URL,
        request_timeout: float = 10.0,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self._http = session
        self._user_id = user_id
        self._api_url = api_url
        self._request_timeout = request_timeout
        self._monotonic = monotonic_clock or time.monotonic

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

    def anonymous_login(self) -> FlashlightSession:
        """Issue a fresh anonymous session, replacing any existing one.

        Named tier-explicitly so a Microsoft-login method can sit
        alongside this one when that lands, without churning callers.
        """
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

        session = _parse_session_response(payload, self._monotonic())
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

        session = _parse_session_response(payload, self._monotonic())
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
        # don't already have one; concurrent calls are safe because
        # anonymous_login() is idempotent (a second login just issues a
        # fresh session).
        if self.current_session is None:
            self.anonymous_login()

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
        self.anonymous_login()
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
        """Start the background thread that refreshes at the session's deadline.

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

            sleep_seconds = max(0.0, session.refresh_at_monotonic - self._monotonic())
            # Cap the maximum sleep so we re-check the session reference
            # periodically (it might have been replaced by reactive
            # refresh / login).
            sleep_seconds = min(sleep_seconds, 600.0)
            if self._stop_event.wait(sleep_seconds):
                return

            # Re-read in case it was replaced while we slept.
            session = self.current_session
            if session is None:
                continue

            try:
                if session.can_refresh:
                    self.refresh()
                else:
                    # Server has told us another /refresh would be
                    # useless: the session's refresh window has been
                    # clamped to the absolute lifetime cap. Skip the
                    # round-trip and re-auth from scratch.
                    self.anonymous_login()
            except FlashlightAuthError as e:
                logger.warning(
                    "Proactive renewal failed; leaving reactive path to recover",
                    exc_info=e,
                )
                # On failure, let the next reactive 401 trigger recovery.
                # Briefly back off before the next loop iteration.
                if self._stop_event.wait(30):
                    return


__all__ = [
    "FlashlightAuthClient",
    "FlashlightAuthError",
    "FlashlightSession",
]
