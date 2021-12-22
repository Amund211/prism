from examples.sidelay.output.overlay_window import CellValue, OverlayRow
from examples.sidelay.stats import PropertyName, Stats


def stats_to_row(stats: Stats) -> OverlayRow[PropertyName]:
    """
    stat_string = stats.get_string(stat_name)
    stat_value = stats.get_value(stat_name)
    """

    return {
        "username": CellValue(stats.get_string("username"), "white"),
        "stars": CellValue(stats.get_string("stars"), "white"),
        "fkdr": CellValue(stats.get_string("fkdr"), "white"),
        "wlr": CellValue(stats.get_string("wlr"), "white"),
        "winstreak": CellValue(stats.get_string("winstreak"), "white"),
    }
