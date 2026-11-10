"""Parse and compare prism version strings."""

import logging
from dataclasses import astuple, dataclass
from typing import Self

from prism import VERSION_STRING

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
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
        if version.startswith("v"):
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


# Ensure current version passes version parsing
_current_version_info = VersionInfo.parse(VERSION_STRING)
assert _current_version_info is not None, "Could not parse current version string"
CURRENT_VERSION_INFO = _current_version_info
del _current_version_info
