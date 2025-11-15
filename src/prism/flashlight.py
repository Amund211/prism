import functools
import logging
from json import JSONDecodeError

import requests
from requests.exceptions import RequestException

from prism.errors import APIError, APIKeyError
from prism.player import Tags, TagSeverity
from prism.ratelimiting import RateLimiter
from prism.requests import make_prism_requests_session
from prism.retry import ExecutionError, execute_with_retry

logger = logging.getLogger(__name__)

FLASHLIGHT_API_URL = "https://flashlight.prismoverlay.com"


class FlashlightTagsProvider:
    def __init__(
        self,
        *,
        retry_limit: int,
        initial_timeout: float,
    ) -> None:
        self._retry_limit = retry_limit
        self._initial_timeout = initial_timeout
        self._session = make_prism_requests_session()
        self._limiter = RateLimiter(limit=120, window=60)

    @property
    def seconds_until_unblocked(self) -> float:
        """Return the number of seconds until we are unblocked"""
        return self._limiter.block_duration_seconds

    def _make_tags_request(
        self,
        *,
        url: str,
        user_id: str,
        last_try: bool,
        urchin_api_key: str | None,
    ) -> requests.Response:  # pragma: nocover
        headers = {"X-User-Id": user_id}
        if urchin_api_key:
            headers["X-Urchin-Api-Key"] = urchin_api_key

        try:
            # Uphold our prescribed rate-limits
            with self._limiter:
                response = self._session.get(url, headers=headers, timeout=10)
        except RequestException as e:
            raise ExecutionError(
                "Request to flashlight failed due to an unknown error"
            ) from e

        if response.status_code == 401:
            raise APIKeyError(
                "Request to flashlight failed with HTTP 401 Unauthorized - "
                "invalid urchin API key"
            )

        if response.status_code == 429 or response.status_code == 503 and not last_try:
            raise ExecutionError(
                "Request to flashlight failed due to intermittent error, retrying"
            )

        return response

    def get_tags(
        self,
        uuid: str,
        *,
        urchin_api_key: str | None,
        user_id: str,
    ) -> Tags:  # pragma: nocover
        """Get the tags for the given player (are they a sniper/cheater)"""
        url = f"{FLASHLIGHT_API_URL}/v1/tags/{uuid}"

        try:
            response = execute_with_retry(
                functools.partial(
                    self._make_tags_request,
                    url=url,
                    user_id=user_id,
                    urchin_api_key=urchin_api_key,
                ),
                retry_limit=self._retry_limit,
                initial_timeout=self._initial_timeout,
            )
        except ExecutionError as e:
            raise APIError(f"Request to flashlight failed for {uuid=}.") from e

        if not response:
            raise APIError(
                f"Request to flashlight failed with status code "
                f"{response.status_code} when getting tags for player {uuid}. "
                f"Response: {response.text}"
            )

        try:
            response_json = response.json()
        except JSONDecodeError as e:
            raise APIError(
                "Failed parsing the response from flashlight. "
                f"Raw content: {response.text}"
            ) from e

        return parse_flashlight_tags(response_json)


def validate_tag_severity(tag_severity: object) -> TagSeverity | None:
    """Validate that the string is a valid TagSeverity"""
    if not isinstance(tag_severity, str):
        return None

    if tag_severity == "none":
        return "none"
    if tag_severity == "medium":
        return "medium"
    if tag_severity == "high":
        return "high"

    return None


def parse_flashlight_tags(response_json: object) -> Tags:
    """Parse the flashlight tags from the response JSON"""
    if not isinstance(response_json, dict):
        raise APIError(f"Invalid response JSON {response_json=} {type(response_json)=}")

    tags_data = response_json.get("tags", {})
    if not isinstance(tags_data, dict):
        raise APIError(f"Invalid tags data {tags_data=} {type(tags_data)=}")

    cheating_severity = validate_tag_severity(tags_data.get("cheating", None))
    if cheating_severity is None:
        raise APIError(
            f"Invalid cheating tag severity " f"{response_json.get('cheating', None)=}"
        )
    sniper_severity = validate_tag_severity(tags_data.get("sniping", None))
    if sniper_severity is None:
        raise APIError(
            f"Invalid sniping tag severity " f"{response_json.get('sniping', None)=}"
        )

    return Tags(
        cheating=cheating_severity,
        sniping=sniper_severity,
    )
