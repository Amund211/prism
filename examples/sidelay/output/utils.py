from typing import Optional, Sequence, Union

from examples.sidelay.stats import PropertyName

COLUMN_NAMES: dict[PropertyName, str] = {
    "username": "IGN",
    "stars": "Stars",
    "fkdr": "FKDR",
    "wlr": "WLR",
    "winstreak": "WS",
}

STAT_LEVELS: dict[PropertyName, Optional[Sequence[Union[int, float]]]] = {
    "stars": (100, 300, 500, 800),
    "fkdr": (0.5, 2, 4, 8),
    "wlr": (0.3, 1, 2, 4),
    "winstreak": (5, 15, 30, 50),
    "username": None,
}


def rate_value(value: Union[int, float], levels: Sequence[Union[int, float]]) -> int:
    """
    Rate the value according to the provided levels (sorted)

    The rating is the smallest index i in levels that is such that
    value < levels[i]
    Alternatively the largest index i in levels such that
    value >= levels[i + 1]
    NOTE: If value >= levels[j] for all j, the rating will be `len(levels)`
    """
    for rating, level in enumerate(levels):
        if value < level:
            break
    else:
        # Passed all levels
        rating += 1

    return rating
