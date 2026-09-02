import math
from dataclasses import dataclass

from prism.flashlight.auth.errors import AuthError

# The shortest delay we will ever schedule a proactive refresh for.
#
# `refreshInSeconds: 0` would otherwise spin: nothing refuses an early refresh,
# so every pass succeeds and hands back another session asking for the same.
# Floors the proactive timer only - see `note_refresh_hint`'s TODO.
MIN_REFRESH_DELAY_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class Session:
    """
    A flashlight auth session

    Clock-free, and deliberately so: it holds the server's *duration*, never a
    deadline. The server only ever sends durations, and `AuthManager` is the one
    place that turns one into a deadline against its own monotonic clock — so
    there is exactly one clock in the whole flow, and nothing in prism ever
    compares wall-clock times. That is what makes NTP skew, a suspended laptop
    and a user changing their clock all non-events.
    """

    session_id: str
    tier: str

    # False once the server knows another refresh would be pointless - it would
    # be clamped to the session's absolute lifetime cap, or refused. The session
    # we are holding is still fully usable; it is the *next* renewal that has to
    # be a fresh login instead of a refresh.
    can_refresh: bool

    # How long from being issued until we should renew it - the server's
    # `refreshInSeconds`, floored.
    refresh_in_seconds: float


def parse_session_response(response_json: object) -> Session:
    """Parse a session out of a login or refresh response"""
    if not isinstance(response_json, dict):
        raise AuthError(f"Invalid session response {response_json=}")

    session_id = response_json.get("sessionId", None)
    if not isinstance(session_id, str) or not session_id:
        raise AuthError(f"Invalid sessionId in session response {session_id=}")

    tier = response_json.get("tier", None)
    if not isinstance(tier, str) or not tier:
        raise AuthError(f"Invalid tier in session response {tier=}")

    can_refresh = response_json.get("canRefresh", None)
    if not isinstance(can_refresh, bool):
        raise AuthError(f"Invalid canRefresh in session response {can_refresh=}")

    refresh_in_seconds = response_json.get("refreshInSeconds", None)
    if (
        isinstance(refresh_in_seconds, bool)
        or not isinstance(refresh_in_seconds, (int, float))
        or not math.isfinite(refresh_in_seconds)
        or refresh_in_seconds < 0
    ):
        raise AuthError(
            f"Invalid refreshInSeconds in session response {refresh_in_seconds=}"
        )

    # `expiresInSeconds` and `refreshUntilInSeconds` are informational only -
    # `refreshInSeconds` is the one the client is meant to act on, so we don't
    # store durations we would never read.
    return Session(
        session_id=session_id,
        tier=tier,
        can_refresh=can_refresh,
        refresh_in_seconds=max(float(refresh_in_seconds), MIN_REFRESH_DELAY_SECONDS),
    )
