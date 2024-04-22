from prism.overlay.output.cells import DEFAULT_COLUMN_ORDER, ColumnName
from prism.overlay.output.printing import SEP, color, get_sep, print_stats_table, title
from tests.prism.overlay.utils import DEFAULT_RATING_CONFIG_COLLECTION, make_player

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


def test_print_stats_table() -> None:
    """Assert that it doesn't throw an error"""
    print_stats_table(
        [make_player()],
        set(),
        DEFAULT_COLUMN_ORDER,
        DEFAULT_RATING_CONFIG_COLLECTION,
        out_of_sync=False,
    )
