from typing import Optional, Sequence, Union

from examples.sidelay.stats import PropertyName

COLUMN_NAMES: dict[str, PropertyName] = {
    "IGN": "username",
    "Stars": "stars",
    "FKDR": "fkdr",
    "WLR": "wlr",
    "WS": "winstreak",
}


STAT_LEVELS: dict[PropertyName, Optional[Sequence[Union[int, float]]]] = {
    "stars": (100, 300, 500, 800),
    "fkdr": (0.5, 2, 4, 8),
    "wlr": (0.3, 1, 2, 4),
    "winstreak": (5, 15, 30, 50),
    "username": None,
}
