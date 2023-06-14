"""Check for updates on GitHub"""

import logging
from dataclasses import astuple, dataclass
from json import JSONDecodeError
from typing import Any, Self

import requests

from prism import VERSION_STRING

logger = logging.getLogger(__name__)


@dataclass
class VersionInfo:
    """
    Class storing the version info from a version string like v1.3.2-dev

    The property dev is True if there is any suffix -<whatever>
    """

    major: int
    minor: int
    patch: int
    dev: bool

    @classmethod
    def parse(cls, version: str) -> Self | None:
        """Parse a version string (or tag name) into (major, minor, patch, dev)"""
        # Remove v
        if version[0] == "v":
            version = version[1:]

        parts = version.split(".")

        if len(parts) != 3:
            logger.error(f"Did not get 3 {parts=}")
            return None

        dev = False
        if "-" in parts[2]:
            index = parts[2].index("-")
            parts[2] = parts[2][:index]
            dev = True

        try:
            numeric_parts = [int(part) for part in parts]
        except ValueError:
            logger.exception(f"Could not convert {parts=} to ints")
            return None

        major, minor, patch = numeric_parts

        return cls(major, minor, patch, dev)

    def update_available(self, latest_version: Self, ignore_patch_bumps: bool) -> bool:
        """Return True if latest_version is later than self"""
        current_version = self
        current_tuple = astuple(self)
        latest_tuple = astuple(latest_version)

        if ignore_patch_bumps:
            return latest_tuple[:2] > current_tuple[:2]

        if latest_tuple[:3] > current_tuple[:3]:
            return True

        if (
            # Versions match
            latest_tuple[:3] == current_tuple[:3]
            # but our version is a development version
            and current_version.dev
            # and the latest one is not
            and not latest_version.dev
        ):
            return True

        return False


def update_available(ignore_patch_bumps: bool) -> bool:  # pragma: no cover
    """Return True if there is an update available on GitHub"""
    return _update_available(
        VERSION_STRING, get_latest_release_tag(), ignore_patch_bumps
    )


def _update_available(
    current_string: str, latest_string: str | None, ignore_patch_bumps: bool
) -> bool:
    """
    Return True if the latest version is compares greater than current_version

    Patch bumps (e.g. 1.3.1 -> 1.3.2) are ignored if ignore_patch_bumps
    """
    if latest_string is None:
        logger.error("Could not get latest release tag. Skipping update check.")
        return False

    current_version = VersionInfo.parse(current_string)
    latest_version = VersionInfo.parse(latest_string)
    if current_version is None or latest_version is None:
        logger.error(
            "Could not parse tags {current_string=} {latest_string=}. "
            "Skipping update check."
        )
        return False

    return current_version.update_available(latest_version, ignore_patch_bumps)


def get_latest_release_tag() -> str | None:  # pragma: no cover
    """Get the tag of the latest release on GitHub"""
    try:
        response = requests.get(
            "https://api.github.com/repos/Amund211/prism/releases?per_page=1",
            headers={"accept": "application/vnd.github+json"},
        )
    except requests.RequestException as e:
        logger.exception("Request failure while getting list of releases.", exc_info=e)
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

    return parse_releases_to_latest_tag(releases)


def parse_releases_to_latest_tag(releases: Any) -> str | None:
    """Parse the response json from the releases api to a tuple of tags"""
    if not isinstance(releases, (list, tuple)) or not releases:
        logger.error(f"{releases=} not iterable or empty")
        return None

    latest = releases[0]

    if not isinstance(latest, dict):
        logger.error(f"{latest=} not a dict")
        return None

    latest_tag = latest.get("tag_name", None)

    if not isinstance(latest_tag, str):
        logger.error(f"{latest_tag=} not a string")
        return None

    return latest_tag
