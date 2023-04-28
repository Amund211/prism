from prism.overlay.output.cells import ColumnName
from prism.overlay.output.printing import SEP, color, get_sep, title

END = "\033[0m"

column_order: tuple[ColumnName, ...] = ("username", "stars", "fkdr", "winstreak")


def test_title() -> None:
    """Title should bold the text"""
    assert title("MYTEXT") == "\033[1m" + "MYTEXT" + END


def test_color() -> None:
    assert color("MYTEXT", "COLOR") == "COLOR" + "MYTEXT" + END


def test_get_sep() -> None:
    assert get_sep("username", column_order) == SEP
    assert get_sep("stars", column_order) == SEP
    assert get_sep("fkdr", column_order) == SEP
    assert get_sep("winstreak", column_order) == "\n"

    assert get_sep("someweirdstring", column_order) == SEP
