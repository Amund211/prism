class TerminalColor:
    """
    SGR color constants
    rene-d 2018

    https://gist.github.com/rene-d/9e584a7dd2935d0f461904b9f2950007
    """

    BLACK = "\033[0;30m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    BROWN = "\033[0;33m"
    BLUE = "\033[0;34m"
    PURPLE = "\033[0;35m"
    CYAN = "\033[0;36m"
    LIGHT_GRAY = "\033[0;37m"
    DARK_GRAY = "\033[1;30m"
    LIGHT_RED = "\033[1;31m"
    LIGHT_GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    LIGHT_BLUE = "\033[1;34m"
    LIGHT_PURPLE = "\033[1;35m"
    LIGHT_CYAN = "\033[1;36m"
    LIGHT_WHITE = "\033[1;37m"

    BG_WHITE = "\033[47;1m"

    BOLD = "\033[1m"
    FAINT = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    NEGATIVE = "\033[7m"
    CROSSED = "\033[9m"
    END = "\033[0m"


class GUIColor:
    """Colors for the GUI"""

    WHITE = "#FFFFFF"


class MinecraftColor:
    """Minecraft chat colors"""

    BLACK = "#000000"  # §0
    DARK_BLUE = "#0000AA"  # §1
    DARK_GREEN = "#00AA00"  # §2
    DARK_AQUA = "#00AAAA"  # §3
    DARK_RED = "#AA0000"  # §4
    DARK_PURPLE = "#AA00AA"  # §5
    GOLD = "#FFAA00"  # §6
    GRAY = "#AAAAAA"  # §7
    DARK_GRAY = "#555555"  # §8
    BLUE = "#5555FF"  # §9
    GREEN = "#55FF55"  # §a
    AQUA = "#55FFFF"  # §b
    RED = "#FF5555"  # §c
    LIGHT_PURPLE = "#FF55FF"  # §d
    YELLOW = "#FFFF55"  # §e
    WHITE = "#FFFFFF"  # §f
