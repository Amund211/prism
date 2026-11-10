import os
from collections.abc import Mapping
from typing import cast

import pytest

from prism.overlay.keybinds import (
    AlphanumericKey,
    AlphanumericKeyDict,
    Key,
    KeyDict,
    LazyString,
    SpecialKey,
    SpecialKeyDict,
    construct_key,
    construct_key_dict,
    create_pynput_normalizer,
)

os.environ["PYNPUT_BACKEND"] = "dummy"

from pynput import keyboard  # noqa: E402

key_to_key_dict_cases: tuple[tuple[Key, KeyDict], ...] = (
    (
        AlphanumericKey(name="b", char="b"),
        {"name": "b", "char": "b", "key_type": "alphanumeric"},
    ),
    (
        AlphanumericKey(name="keyname", char="character"),
        {"name": "keyname", "char": "character", "key_type": "alphanumeric"},
    ),
    (
        SpecialKey(name="tab", vk=12345),
        {"name": "tab", "vk": 12345, "key_type": "special"},
    ),
    (
        SpecialKey(name="missingkey", vk=None),
        {"name": "missingkey", "vk": None, "key_type": "special"},
    ),
)


@pytest.mark.parametrize("key, key_dict", key_to_key_dict_cases)
def test_key_to_dict(key: Key, key_dict: KeyDict) -> None:
    assert key.to_dict() == key_dict


@pytest.mark.parametrize("key, key_dict", key_to_key_dict_cases)
def test_construct_key(key: Key, key_dict: KeyDict) -> None:
    assert construct_key(key_dict) == key


def test_lazy_string() -> None:
    def raise_error() -> str:
        raise ValueError

    # Make sure it's lazy
    LazyString(raise_error)

    assert str(LazyString(lambda: "STRING")) == "STRING"


dict_to_key_dict_cases = (
    (
        {
            "name": "keyname",
            "char": "b",
            "key_type": "alphanumeric",
            "extra": "junk",
            "noonecares": 234987,
        },
        AlphanumericKeyDict(name="keyname", char="b", key_type="alphanumeric"),
    ),
    (
        {
            "name": "keyname",
            "vk": 123,
            "key_type": "special",
            "extra": "junk",
            "noonecares": 234987,
        },
        SpecialKeyDict(name="keyname", vk=123, key_type="special"),
    ),
    ({"name": "keyname", "vk": 123, "char": "k", "key_type": "wrongtype"}, None),
    ({"name": "tab", "vk": "stringvk", "key_type": "special"}, None),
    ({"name": "missingkey", "vk": None, "key_type": "alphanumeric"}, None),
    ({"name": "missingkey", "char": 123, "key_type": "alphanumeric"}, None),
    ({"name": 123, "char": "c", "key_type": "alphanumeric"}, None),
    ({"name": 123, "vk": "c", "key_type": "alphanumeric"}, None),
    *((key_dict, key_dict) for key, key_dict in key_to_key_dict_cases),
)


@pytest.mark.parametrize("source_dict, key_dict", dict_to_key_dict_cases)
def test_construct_key_dict(
    source_dict: Mapping[str, object], key_dict: KeyDict
) -> None:
    assert construct_key_dict(source_dict) == key_dict


pynput_normalizer = create_pynput_normalizer()


def create_pynput_key(name: str, vk: int) -> keyboard.Key:
    """Create a an object masquerading as a keyboard.Key instance"""

    class MockedKey:
        """Hack to pass isinstance checks"""

        __class__ = keyboard.Key  # type: ignore [assignment]

        def __init__(self, name: str, vk: int) -> None:
            self.name = name
            self.value = keyboard.KeyCode.from_vk(vk)

    return cast(keyboard.Key, MockedKey(name, vk))


@pytest.mark.parametrize(
    "pynput_key, key",
    (
        (keyboard.KeyCode.from_char("a"), AlphanumericKey(name="a", char="a")),
        (keyboard.KeyCode.from_char("A"), AlphanumericKey(name="a", char="a")),
        (create_pynput_key("tab", 123), SpecialKey(name="tab", vk=123)),
        (keyboard.KeyCode.from_vk(1234), SpecialKey(name="<1234>", vk=1234)),
        (None, None),
    ),
)
def test_pynput_normalizer(
    pynput_key: keyboard.Key | keyboard.KeyCode | None, key: Key | None
) -> None:
    assert pynput_normalizer(pynput_key) == key
