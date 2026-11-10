import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypeAlias, TypedDict

if TYPE_CHECKING:  # pragma: no coverage
    from pynput import keyboard


logger = logging.getLogger(__name__)


class AlphanumericKeyDict(TypedDict):
    name: str
    char: str
    key_type: Literal["alphanumeric"]


@dataclass(frozen=True, slots=True)
class AlphanumericKey:
    name: str = field(compare=False)
    char: str

    def to_dict(self) -> AlphanumericKeyDict:
        return {"name": self.name, "char": self.char, "key_type": "alphanumeric"}


class SpecialKeyDict(TypedDict):
    name: str
    vk: int | None
    key_type: Literal["special"]


@dataclass(frozen=True, slots=True)
class SpecialKey:
    name: str = field(compare=False)
    vk: int | None

    def to_dict(self) -> SpecialKeyDict:
        return {"name": self.name, "vk": self.vk, "key_type": "special"}


Key: TypeAlias = AlphanumericKey | SpecialKey
KeyDict: TypeAlias = AlphanumericKeyDict | SpecialKeyDict


def construct_key(key_dict: KeyDict) -> Key:
    """Construct a Key object from a KeyDict"""
    if key_dict["key_type"] == "special":
        return SpecialKey(name=key_dict["name"], vk=key_dict["vk"])
    return AlphanumericKey(name=key_dict["name"], char=key_dict["char"])


def construct_key_dict(source_dict: Mapping[str, object]) -> KeyDict | None:
    key_type = source_dict.get("key_type", None)
    name = source_dict.get("name", None)

    if not isinstance(name, str):
        return None

    if key_type == "special":
        vk = source_dict.get("vk", None)
        if vk is None or isinstance(vk, int):
            return SpecialKeyDict(name=name, vk=vk, key_type="special")
    elif key_type == "alphanumeric":
        char = source_dict.get("char", None)
        if isinstance(char, str):
            return AlphanumericKeyDict(
                name=name, char=char.lower(), key_type="alphanumeric"
            )

    return None


class LazyString:
    """
    A lazily evaluated string

    Useful for passing expensive computations to loggers
    NOTE: Exceptions raised in the call to __str__ will be caught by the logger
    """

    def __init__(self, func: Callable[[], str]) -> None:
        self.func = func

    def __str__(self) -> str:
        return self.func()


def create_pynput_normalizer() -> (
    Callable[["keyboard.Key | keyboard.KeyCode | None"], Key | None]
):
    """Create a function normalizing pynput Keys/KeyCodes to our internal Key"""
    try:
        from pynput import keyboard
    except Exception:  # pragma: no coverage
        logger.exception("Failed to import pynput")

        def normalize_to_unknown(key: object) -> Key | None:
            return SpecialKey(name="<unknown>", vk=None)

        return normalize_to_unknown

    def normalize(key: keyboard.Key | keyboard.KeyCode | None) -> Key | None:
        if key is None:
            return None

        if isinstance(key, keyboard.Key):
            return SpecialKey(name=key.name, vk=key.value.vk)

        keycode = key

        if keycode.char is not None:
            char = keycode.char.lower()
            return AlphanumericKey(name=char, char=char)

        if keycode.vk is not None:
            return SpecialKey(name=f"<{keycode.vk}>", vk=keycode.vk)

        # vk == None should be unreachable
        logger.warning(  # pragma: no coverage
            "Could not normalize KeyCode %s, %s",
            keycode,
            LazyString(
                lambda: ", ".join(
                    f"{extension}={getattr(keycode, extension)}"
                    for extension in keycode._PLATFORM_EXTENSIONS
                )
            ),
        )

        return None  # pragma: no coverage

    return normalize
