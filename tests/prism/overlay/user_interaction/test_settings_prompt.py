from collections.abc import Mapping

import pytest

from prism.overlay.keybinds import AlphanumericKey, Key
from prism.overlay.settings import Settings, fill_missing_settings
from prism.overlay.user_interaction.settings_prompt import prompt_if_no_autowho
from tests.prism.overlay.test_settings import make_settings_dict
from tests.prism.overlay.utils import make_settings


def alphanumeric_key(char: str) -> Key:
    return AlphanumericKey(name=char, char=char)


@pytest.mark.parametrize(
    "settings, incomplete_settings, result, should_update",
    (
        # Not updated
        (make_settings(), {"autowho": True}, make_settings(), False),
        (
            make_settings(autowho=False, chat_hotkey=alphanumeric_key("u")),
            {"autowho": False},
            make_settings(autowho=False, chat_hotkey=alphanumeric_key("u")),
            False,
        ),
        # Important that the default settings don't lead to an update
        (make_settings(), make_settings_dict(), make_settings(), False),
        (make_settings(), fill_missing_settings({}, 10)[0], make_settings(), False),
        # Invalid value for autowho, but probably not first launch
        (make_settings(), {"autowho": ""}, make_settings(), False),
        # Updated
        # NOTE: Update called, but settings are the same
        (
            make_settings(chat_hotkey=alphanumeric_key("r")),
            {},
            make_settings(chat_hotkey=alphanumeric_key("r")),
            True,
        ),
        (
            make_settings(autowho=False, chat_hotkey=alphanumeric_key("u")),
            {},
            make_settings(autowho=True, chat_hotkey=alphanumeric_key("r")),
            True,
        ),
        (
            make_settings(chat_hotkey=alphanumeric_key("l")),
            {},
            make_settings(chat_hotkey=alphanumeric_key("r")),
            True,
        ),
        (
            make_settings(autowho=False),
            {},
            make_settings(chat_hotkey=alphanumeric_key("r")),
            True,
        ),
        # Values in incomplete are ignored
        (
            make_settings(autowho=False, chat_hotkey=alphanumeric_key("u")),
            {"chat_hotkey": alphanumeric_key("x").to_dict()},
            make_settings(chat_hotkey=alphanumeric_key("r")),
            True,
        ),
    ),
)
def test_prompt_if_no_autowho(
    settings: Settings,
    incomplete_settings: Mapping[str, object],
    result: Settings,
    should_update: bool,
) -> None:
    def prompt(settings: Settings) -> tuple[bool, Key]:
        return True, alphanumeric_key("r")

    new_settings, updated = prompt_if_no_autowho(
        settings, incomplete_settings, prompt=prompt
    )
    assert new_settings == result
    assert updated == should_update
