import pytest

from prism.mojang import MojangAccountProvider, compare_uuids


@pytest.mark.parametrize(
    "uuid_1, uuid_2, equal",
    (
        (
            "4cea508d-954d-4261-8f07-4b7494ca1d02",
            "4cea508d-954d-4261-8f07-4b7494ca1d02",
            True,
        ),
        (
            "4cea508d-954d-4261-8f07-4b7494ca1d02",
            "4cea508d954d42618f074b7494ca1d02",
            True,
        ),
        (
            "4cea508d954d42618f074b7494ca1d02",
            "4cea508d-954d-4261-8f07-4b7494ca1d02",
            True,
        ),
        ("4cea508d954d42618f074b7494ca1d02", "4cea508d954d42618f074b7494ca1d02", True),
        ("4cea508d954d42618f074", "4cea508d954d42618f074b7494ca1d02", False),
        (
            "abcabcabc4cea508d-954d-4261-8f07-4b7494ca1d02",
            "4cea508d-954d-4261-8f07-4b7494ca1d02",
            False,
        ),
        ("", "4cea508d-954d-4261-8f07-4b7494ca1d02", False),
    ),
)
def test_compare_uuids(uuid_1: str, uuid_2: str, equal: bool) -> None:
    assert compare_uuids(uuid_1, uuid_2) is equal


def test_make_provider() -> None:
    MojangAccountProvider(retry_limit=3, initial_timeout=1.0)
