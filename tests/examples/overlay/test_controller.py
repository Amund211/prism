from examples.overlay.controller import RealOverlayController
from examples.overlay.nick_database import NickDatabase
from tests.examples.overlay.utils import create_state, make_settings


def test_real_overlay_controller() -> None:
    controller = RealOverlayController(
        state=create_state(),
        settings=make_settings(
            hypixel_api_key="hypixel_key",
            antisniper_api_key="antisniper_key",
            use_antisniper_api=True,
        ),
        nick_database=NickDatabase([{}]),
    )

    assert controller.hypixel_key_holder.key == "hypixel_key"

    assert controller.antisniper_key_holder is not None
    assert controller.antisniper_key_holder.key == "antisniper_key"

    controller.set_hypixel_api_key("new_key")
    assert controller.hypixel_key_holder.key == "new_key"

    # set -> set
    controller.set_antisniper_api_key("new_key")
    assert controller.antisniper_key_holder.key == "new_key"

    # set -> unset
    controller.set_antisniper_api_key(None)
    assert controller.antisniper_key_holder is None

    # unset -> unset
    controller.set_antisniper_api_key(None)
    assert controller.antisniper_key_holder is None

    # unset -> set
    controller.set_antisniper_api_key("new_key")
    assert controller.antisniper_key_holder.key == "new_key"

    # Disable antisniper
    controller.settings.use_antisniper_api = False
    # The key holder will remain, but the controller should not use it
    # when denicking or getting winstreaks
    assert controller.antisniper_key_holder.key == "new_key"
