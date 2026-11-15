# LWJGL: LWJGL 2 (1.8.9). GLFW30: GLFW (1.13+). SDL_app: SDL (26.3+)
_MC_ONLY_CLASSES = frozenset(("LWJGL",))
_SHARED_CLASSES = frozenset(("GLFW30", "SDL_app"))

# Other GLFW/SDL apps share the class, so check the title too
_TITLE_PREFIXES = ("Minecraft", "Lunar Client")


def is_minecraft_window(class_name: str, title: str) -> bool:
    """Return True if the window class and title belong to a Minecraft game window"""
    if class_name in _MC_ONLY_CLASSES:
        return True
    if class_name in _SHARED_CLASSES:
        return title.startswith(_TITLE_PREFIXES)
    return False
