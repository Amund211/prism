import pytest

from prism.version import VersionInfo


@pytest.mark.parametrize(
    "version_string, result",
    (
        ("v1.0.0", VersionInfo(1, 0, 0, False)),
        ("v1.0.1", VersionInfo(1, 0, 1, False)),
        ("v1.1.1", VersionInfo(1, 1, 1, False)),
        ("v2.1.1", VersionInfo(2, 1, 1, False)),
        ("v1.3.1-dev", VersionInfo(1, 3, 1, True)),
        ("v1.3.1-lol", VersionInfo(1, 3, 1, True)),
        # Invalid strings
        ("v1.2.3.4.5", None),
        ("va.b.c", None),
        ("", None),
    ),
)
def test_versioninfo_parse(version_string: str, result: VersionInfo | None) -> None:
    assert VersionInfo.parse(version_string) == result


@pytest.mark.parametrize(
    "current_string, latest_string, minor_bump, patch_bump",
    (
        ("v2.1.0", "v2.1.0", False, False),
        ("v2.0.0", "v2.1.0", True, True),
        ("v1.0.1", "v2.1.0", True, True),
        ("v1.0.0", "v2.1.0", True, True),
        ("v2.1.0", "v2.1.1", False, True),
        ("v1.0.1-dev", "v1.0.1", False, True),
    ),
)
def test_update_available(
    current_string: str, latest_string: str, minor_bump: bool, patch_bump: bool
) -> None:
    current = VersionInfo.parse(current_string)
    latest = VersionInfo.parse(latest_string)
    assert current is not None
    assert latest is not None

    assert current.update_available(latest, ignore_patch_bumps=True) == minor_bump
    assert current.update_available(latest, ignore_patch_bumps=False) == patch_bump
