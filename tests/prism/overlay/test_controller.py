from prism.overlay.controller import RealOverlayController
from prism.overlay.nick_database import NickDatabase
from tests.prism.overlay.utils import create_state, make_settings


def test_real_overlay_controller() -> None:
    controller = RealOverlayController(
        state=create_state(),
        settings=make_settings(
            antisniper_api_key="antisniper_key",
            use_antisniper_api=True,
        ),
        nick_database=NickDatabase([{}]),
    )

    assert controller.antisniper_key_holder.key == "antisniper_key"
