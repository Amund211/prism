import pytest

from prism.overlay.tabshot.window import exe_name, is_minecraft_candidate


@pytest.mark.parametrize(
    "exe, name",
    (
        ("C:\\Program Files\\Java\\bin\\javaw.exe", "javaw.exe"),
        ("/usr/lib/jvm/java-8/bin/java", "java"),
        ("java", "java"),
    ),
)
def test_exe_name(exe: str, name: str) -> None:
    assert exe_name(exe) == name


@pytest.mark.parametrize(
    "exe, window_class, title, result",
    (
        ("C:\\x\\javaw.exe", "LWJGL", "Minecraft 1.8.9", True),
        (None, "LWJGL", "", True),
        (None, "GLFW30", "", True),
        (None, None, "Lunar Client 1.8.9", True),
        ("/usr/bin/java", None, "", True),
        ("C:\\x\\Lunar Client.exe", None, "", True),
        ("C:\\x\\firefox.exe", "MozillaWindowClass", "Hypixel Forums", False),
        (None, None, "", False),
    ),
)
def test_is_minecraft_candidate(
    exe: str | None, window_class: str | None, title: str, result: bool
) -> None:
    assert (
        is_minecraft_candidate(exe=exe, window_class=window_class, title=title)
        is result
    )
