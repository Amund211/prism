from collections.abc import Mapping

import pytest

from prism.overlay.keybinds import AlphanumericKey, Key
from prism.overlay.settings import Settings
from prism.overlay.user_interaction.settings_prompt import prompt_if_no_autowho
from tests.prism.overlay.test_settings import make_settings_dict
from tests.prism.overlay.utils import make_settings


def alphanumeric_key(char: str) -> Key:
    return AlphanumericKey(name=char, char=char)


@pytest.mark.parametrize(
    "settings, incomplete_settings, result, should_update",
    (
        (make_settings(), {"autowho": True}, make_settings(), False),
        (make_settings(), {"autowho": False}, make_settings(), False),
        (make_settings(), make_settings_dict(), make_settings(), False),
        # Invalid value for autowho, but probably not first launch
        (make_settings(), {"autowho": ""}, make_settings(), False),
        (
            make_settings(autowho=False, chat_hotkey=alphanumeric_key("u")),
            {},
            make_settings(),
            True,
        ),
        (make_settings(chat_hotkey=alphanumeric_key("u")), {}, make_settings(), True),
        (make_settings(autowho=False), {}, make_settings(), True),
        # Values in incomplete are ignored
        (
            make_settings(autowho=False, chat_hotkey=alphanumeric_key("u")),
            {"chat_hotkey": alphanumeric_key("x").to_dict()},
            make_settings(),
            True,
        ),
        # Same as default
        (make_settings(), {}, make_settings(), False),
    ),
)
def test_prompt_if_no_autowho(
    settings: Settings,
    incomplete_settings: Mapping[str, object],
    result: Settings,
    should_update: bool,
) -> None:
    def prompt(settings: Settings) -> tuple[bool, Key]:
        return True, AlphanumericKey(name="t", char="t")

    new_settings, updated = prompt_if_no_autowho(
        settings, incomplete_settings, prompt=prompt
    )
    assert new_settings == result
    assert updated == should_update
