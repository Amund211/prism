import pytest

from prism.overlay.platform.minecraft_window import is_minecraft_window


@pytest.mark.parametrize(
    "class_name, title, result",
    (
        # Window class/title pairs seen in real tabshot captures
        ("LWJGL", "Minecraft 1.8.9", True),
        ("LWJGL", "Lunar Client 1.8.9 (v2.23.13-2645)", True),
        ("SDL_app", "Minecraft* 26.3", True),
        ("SDL_app", "Minecraft* 26.3 - Multiplayer (3rd-party Server)", True),
        ("Chrome_WidgetWin_1", "Mission Control - Lunar Client", False),
        ("Chrome_WidgetWin_1", "Home - Lunar Client", False),
        # Synthetic: GLFW (1.13 - 26.2)
        ("GLFW30", "Minecraft 1.21.4", True),
        ("GLFW30", "Lunar Client 1.21.4 (v2.23.13-2645)", True),
        # Synthetic: any title starting with Minecraft / Lunar Client
        ("GLFW30", "Minecraft", True),
        ("SDL_app", "MinecraftSomething", True),
        ("SDL_app", "Lunar Client", True),
        # Synthetic: other GLFW/SDL apps
        ("GLFW30", "Some other game", False),
        ("SDL_app", "Some other game", False),
        ("Notepad", "Minecraft 1.8.9", False),
    ),
)
def test_is_minecraft_window(class_name: str, title: str, result: bool) -> None:
    assert is_minecraft_window(class_name, title) is result
