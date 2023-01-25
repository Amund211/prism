"""Check for updates on GitHub"""

import logging
from json import JSONDecodeError
from typing import Any

import requests

from prism import VERSION_STRING

logger = logging.getLogger(__name__)


def update_available() -> bool:  # pragma: no cover
    """Return True if there is an update available on GitHub"""
    return _update_available(VERSION_STRING, get_release_tags())


def _update_available(current_version: str, tags: tuple[str, ...] | None) -> bool:
    """
    Return True if a version newer than current_version exists in tags

    Note: we determine the order of releases by the order in the tags list, relying
          on GitHub to send them newest -> oldest. We also check for this by seeing
          if the oldest release is "v1.0.0".
    """
    if tags is None:
        logger.error("Could not get release tags. Skipping update check.")
        return False

    if tags[-1] != "v1.0.0":
        logger.error(
            f"Tag order is not newest -> oldest. {tags=}. Skipping update check."
        )
        return False

    if current_version not in tags:
        logger.debug(
            f"Current version ({current_version}) not found in releases ({tags}). "
            "Skipping update check."
        )
        return False

    return current_version != tags[0]


def get_release_tags() -> tuple[str, ...] | None:  # pragma: no cover
    """Get the tag of all (max 100) current releases on GitHub"""
    try:
        response = requests.get(
            "https://api.github.com/repos/Amund211/prism/releases?per_page=100",
            headers={"accept": "application/vnd.github+json"},
        )
    except requests.RequestException:
        logger.exception("Request failure while getting list of releases.")
        return None

    if not response:
        logger.error(
            f"Failed to get list of releases. {response.status_code=}. {response.text}."
        )
        return None

    try:
        releases = response.json()
    except JSONDecodeError:
        logger.error(
            "Failed parsing the response from the releases endpoint. "
            f"Raw content: {response.text}"
        )
        return None

    return parse_releases_to_tags(releases)


def parse_releases_to_tags(releases: Any) -> tuple[str, ...] | None:
    """Parse the response json from the releases api to a tuple of tags"""
    try:
        return tuple(str(release["tag_name"]) for release in releases)
    except Exception:
        # Potential failures:
        #   releases not iterable
        #   release elements not dictionaries
        #   tag_name key missing
        #   tag_name not convertible to str
        logger.exception("Invalid response from releases endpoint. {releases=}.")
        return None
