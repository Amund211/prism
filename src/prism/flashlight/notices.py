import logging
import time
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Any, Callable, Literal

import requests
from requests.exceptions import RequestException

from prism import VERSION_STRING
from prism.flashlight.url import FLASHLIGHT_API_URL
from prism.requests import make_prism_requests_session

logger = logging.getLogger(__name__)

Severity = Literal["info", "warning", "critical"]


@dataclass(frozen=True, slots=True)
class FlashlightNotice:
    message: str
    severity: Severity

    url: str | None

    created_at_seconds: float
    duration_seconds: float | None

    _get_time_seconds: Callable[[], float] = field(
        compare=False, repr=False, hash=False, default=time.monotonic
    )

    @classmethod
    def create(
        cls,
        message: str,
        severity: Severity,
        url: str | None,
        duration_seconds: float | None,
        get_time_seconds: Callable[[], float],
    ) -> "FlashlightNotice":
        """Create a new FlashlightNotice instance"""
        return cls(
            message=message,
            severity=severity,
            url=url,
            created_at_seconds=get_time_seconds(),
            duration_seconds=duration_seconds,
            _get_time_seconds=get_time_seconds,
        )

    @property
    def active(self) -> bool:
        """Whether the notice is active (i.e., not dismissed)"""
        if self.duration_seconds is None:
            return True

        seconds_since_init = self._get_time_seconds() - self.created_at_seconds
        return seconds_since_init <= self.duration_seconds


def _make_flashlight_notices_request(
    session: requests.Session,
    *,
    user_id: str,
) -> Any | None:  # pragma: nocover
    headers = {
        "X-User-Id": user_id,
        "X-Prism-Version": VERSION_STRING,
    }

    try:
        response = session.get(
            f"{FLASHLIGHT_API_URL}/v1/prism-notices", headers=headers, timeout=30
        )
    except RequestException:
        logger.exception("Failed to request flashlight notices")
        return None

    if not response.ok:
        logger.error(
            f"Flashlight notices request failed with "
            f"status code {response.status_code}"
        )
        return None

    if response.status_code == 204:
        return None

    try:
        return response.json()
    except JSONDecodeError:
        logger.exception("Failed parsing the response from flashlight notices")
        return None


def _parse_flashlight_notice(
    item: object,
    get_time_seconds: Callable[[], float],
) -> FlashlightNotice | None:
    """Parse a single flashlight prism notice from the response JSON"""
    if not isinstance(item, dict):
        logger.error(f"Invalid flashlight notice: " f"{item=} {type(item)=}")
        return None

    raw_message = item.get("message", None)
    if not isinstance(raw_message, str):
        logger.error(f"Invalid flashlight notice message: {raw_message=}")
        return None

    raw_url = item.get("url", None)
    if raw_url is not None and not isinstance(raw_url, str):
        logger.error(f"Invalid flashlight notice url: {raw_url=}")
        return None

    raw_severity = item.get("severity", None)
    if raw_severity not in ("info", "warning", "critical"):
        logger.error(f"Invalid flashlight notice severity: {raw_severity=}")
        return None

    duration_seconds = item.get("duration_seconds", None)
    if duration_seconds is not None and not isinstance(duration_seconds, (int, float)):
        logger.error(f"Invalid flashlight notice duration_seconds: {duration_seconds=}")
        return None

    return FlashlightNotice.create(
        message=raw_message,
        url=raw_url,
        severity=raw_severity,
        duration_seconds=duration_seconds,
        get_time_seconds=get_time_seconds,
    )


def _parse_flashlight_notices(
    response_json: object,
    get_time_seconds: Callable[[], float],
) -> tuple[FlashlightNotice, ...]:
    """Parse the flashlight prism notices from the response JSON"""
    if not isinstance(response_json, dict):
        logger.error(
            f"Invalid flashlight information response: "
            f"{response_json=} {type(response_json)=}"
        )
        return ()

    notices = response_json.get("notices", None)
    if not isinstance(notices, list):
        logger.error(
            f"Invalid flashlight information response: "
            f"{response_json=} {type(response_json)=}"
        )
        return ()

    return tuple(
        notice
        for item in notices
        if (notice := _parse_flashlight_notice(item, get_time_seconds)) is not None
    )


def get_flashlight_notices(
    *,
    user_id: str,
) -> tuple[FlashlightNotice, ...]:  # pragma: nocover
    """Get flashlight prism notices for the user"""
    session = make_prism_requests_session()  # TODO: reuse shared session

    response_json = _make_flashlight_notices_request(
        session=session,
        user_id=user_id,
    )

    if response_json is None:
        return ()

    return _parse_flashlight_notices(response_json, get_time_seconds=time.monotonic)
