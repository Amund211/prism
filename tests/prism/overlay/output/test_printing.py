from prism.overlay.output.printing import SEP, color, get_sep, title

END = "\033[0m"


def test_title() -> None:
    """Title should bold the text"""
    assert title("MYTEXT") == "\033[1m" + "MYTEXT" + END


def test_color() -> None:
    assert color("MYTEXT", "COLOR") == "COLOR" + "MYTEXT" + END


def test_get_sep() -> None:
    assert get_sep("username") == SEP
    assert get_sep("stars") == SEP
    assert get_sep("fkdr") == SEP
    assert get_sep("someweirdstring") == SEP
    assert get_sep("winstreak") == "\n"
