from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Self, TypedDict


class RatingConfigDict(TypedDict):
    """Dict representing a RatingConfig"""

    type: Literal["level_based"]
    rate_by_level: bool
    levels: tuple[float, ...]
    decimals: int
    sort_ascending: bool


def read_rating_config_dict(
    source: Mapping[str, object], default: "RatingConfig"
) -> tuple[RatingConfigDict, bool]:
    """Read a RatingConfigDict from the source mapping"""
    source_updated = False

    if source.get("type", None) != "level_based":
        source_updated = True

    rate_by_level = source.get("rate_by_level", None)
    if not isinstance(rate_by_level, bool):
        rate_by_level = default.rate_by_level
        source_updated = True

    levels = source.get("levels", None)
    if not isinstance(levels, (list, tuple)) or not all(
        isinstance(el, float) for el in levels
    ):
        levels = default.levels
        source_updated = True

    decimals = source.get("decimals", None)
    if not isinstance(decimals, int) or decimals < 0:
        decimals = default.decimals
        source_updated = True

    sort_ascending = source.get("sort_ascending", None)
    if not isinstance(sort_ascending, bool):
        sort_ascending = default.sort_ascending
        source_updated = True

    return {
        "type": "level_based",
        "rate_by_level": rate_by_level,
        "levels": tuple(levels),
        "decimals": decimals,
        "sort_ascending": sort_ascending,
    }, source_updated


def safe_read_rating_config_dict(
    source: object, default: "RatingConfig"
) -> tuple[RatingConfigDict, bool]:
    if not isinstance(source, dict):
        source = {}
    return read_rating_config_dict(source, default)


@dataclass(frozen=True, slots=True)
class RatingConfig:
    """Configuration for how to rate one stat"""

    rate_by_level: bool
    levels: tuple[float, ...]
    decimals: int
    sort_ascending: bool

    def __post_init__(self) -> None:
        """Validate parameters"""
        if self.decimals < 0:
            raise ValueError(f"Invalid value for {self.decimals=}")

    @classmethod
    def from_dict(cls, source: RatingConfigDict) -> Self:
        return cls(
            rate_by_level=source["rate_by_level"],
            levels=source["levels"],
            decimals=source["decimals"],
            sort_ascending=source["sort_ascending"],
        )

    def to_dict(self) -> RatingConfigDict:
        return {
            "type": "level_based",
            "rate_by_level": self.rate_by_level,
            "levels": self.levels,
            "decimals": self.decimals,
            "sort_ascending": self.sort_ascending,
        }


DEFAULT_STARS_CONFIG = RatingConfig(
    rate_by_level=False,
    levels=(100.0, 300.0, 500.0, 800.0),
    decimals=2,
    sort_ascending=False,
)
DEFAULT_FKDR_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(1.0, 2.0, 4.0, 8.0),
    decimals=2,
    sort_ascending=False,
)
DEFAULT_INDEX_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(100.0, 1_200.0, 8_000.0, 51_200.0),
    decimals=0,
    sort_ascending=False,
)
DEFAULT_KDR_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(1.0, 1.5, 2.0, 3.0),
    decimals=2,
    sort_ascending=False,
)
DEFAULT_BBLR_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(0.3, 1.0, 2.0, 4.0),
    decimals=2,
    sort_ascending=False,
)
DEFAULT_WLR_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(0.3, 1.0, 2.0, 4.0),
    decimals=2,
    sort_ascending=False,
)
DEFAULT_WINSTREAK_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(3.0, 5.0, 10.0, 20.0),
    decimals=0,
    sort_ascending=False,
)
DEFAULT_KILLS_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(5_000.0, 10_000.0, 20_000.0, 40_000.0),
    decimals=0,
    sort_ascending=False,
)
DEFAULT_FINALS_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(5_000.0, 10_000.0, 20_000.0, 40_000.0),
    decimals=0,
    sort_ascending=False,
)
DEFAULT_BEDS_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(2_000.0, 5_000.0, 10_000.0, 20_000.0),
    decimals=0,
    sort_ascending=False,
)
DEFAULT_WINS_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(1_000.0, 3_000.0, 6_000.0, 10_000.0),
    decimals=0,
    sort_ascending=False,
)
DEFAULT_SESSIONTIME_CONFIG = RatingConfig(
    rate_by_level=True,
    levels=(60.0, 30.0, 10.0, 5.0),
    decimals=0,
    sort_ascending=True,
)


class RatingConfigCollectionDict(TypedDict):
    """Dict representing a RatingConfigCollection"""

    stars: RatingConfigDict
    index: RatingConfigDict
    fkdr: RatingConfigDict
    kdr: RatingConfigDict
    bblr: RatingConfigDict
    wlr: RatingConfigDict
    winstreak: RatingConfigDict
    kills: RatingConfigDict
    finals: RatingConfigDict
    beds: RatingConfigDict
    wins: RatingConfigDict
    sessiontime: RatingConfigDict


def read_rating_config_collection_dict(
    source: Mapping[str, object]
) -> tuple[RatingConfigCollectionDict, bool]:
    """Read a RatingConfigCollectionDict from the source mapping"""
    any_source_updated = False

    stars, source_updated = safe_read_rating_config_dict(
        source.get("stars", None), default=DEFAULT_STARS_CONFIG
    )
    any_source_updated |= source_updated

    index, source_updated = safe_read_rating_config_dict(
        source.get("index", None), default=DEFAULT_INDEX_CONFIG
    )
    any_source_updated |= source_updated

    fkdr, source_updated = safe_read_rating_config_dict(
        source.get("fkdr", None), default=DEFAULT_FKDR_CONFIG
    )
    any_source_updated |= source_updated

    kdr, source_updated = safe_read_rating_config_dict(
        source.get("kdr", None), default=DEFAULT_KDR_CONFIG
    )
    any_source_updated |= source_updated

    bblr, source_updated = safe_read_rating_config_dict(
        source.get("bblr", None), default=DEFAULT_BBLR_CONFIG
    )
    any_source_updated |= source_updated

    wlr, source_updated = safe_read_rating_config_dict(
        source.get("wlr", None), default=DEFAULT_WLR_CONFIG
    )
    any_source_updated |= source_updated

    winstreak, source_updated = safe_read_rating_config_dict(
        source.get("winstreak", None), default=DEFAULT_WINSTREAK_CONFIG
    )
    any_source_updated |= source_updated

    kills, source_updated = safe_read_rating_config_dict(
        source.get("kills", None), default=DEFAULT_KILLS_CONFIG
    )
    any_source_updated |= source_updated

    finals, source_updated = safe_read_rating_config_dict(
        source.get("finals", None), default=DEFAULT_FINALS_CONFIG
    )
    any_source_updated |= source_updated

    beds, source_updated = safe_read_rating_config_dict(
        source.get("beds", None), default=DEFAULT_BEDS_CONFIG
    )
    any_source_updated |= source_updated

    wins, source_updated = safe_read_rating_config_dict(
        source.get("wins", None), default=DEFAULT_WINS_CONFIG
    )
    any_source_updated |= source_updated

    sessiontime, source_updated = safe_read_rating_config_dict(
        source.get("sessiontime", None), default=DEFAULT_SESSIONTIME_CONFIG
    )
    any_source_updated |= source_updated

    return {
        "stars": stars,
        "index": index,
        "fkdr": fkdr,
        "kdr": kdr,
        "bblr": bblr,
        "wlr": wlr,
        "winstreak": winstreak,
        "kills": kills,
        "finals": finals,
        "beds": beds,
        "wins": wins,
        "sessiontime": sessiontime,
    }, any_source_updated


def safe_read_rating_config_collection_dict(
    source: object,
) -> tuple[RatingConfigCollectionDict, bool]:
    if not isinstance(source, dict):
        source = {}
    return read_rating_config_collection_dict(source)


@dataclass(frozen=True, slots=True)
class RatingConfigCollection:
    """RatingConfig instances for all stats"""

    stars: RatingConfig
    index: RatingConfig
    fkdr: RatingConfig
    kdr: RatingConfig
    bblr: RatingConfig
    wlr: RatingConfig
    winstreak: RatingConfig
    kills: RatingConfig
    finals: RatingConfig
    beds: RatingConfig
    wins: RatingConfig
    sessiontime: RatingConfig

    @classmethod
    def from_dict(cls, source: RatingConfigCollectionDict) -> Self:
        return cls(
            stars=RatingConfig.from_dict(source["stars"]),
            index=RatingConfig.from_dict(source["index"]),
            fkdr=RatingConfig.from_dict(source["fkdr"]),
            kdr=RatingConfig.from_dict(source["kdr"]),
            bblr=RatingConfig.from_dict(source["bblr"]),
            wlr=RatingConfig.from_dict(source["wlr"]),
            winstreak=RatingConfig.from_dict(source["winstreak"]),
            kills=RatingConfig.from_dict(source["kills"]),
            finals=RatingConfig.from_dict(source["finals"]),
            beds=RatingConfig.from_dict(source["beds"]),
            wins=RatingConfig.from_dict(source["wins"]),
            sessiontime=RatingConfig.from_dict(source["sessiontime"]),
        )

    def to_dict(self) -> RatingConfigCollectionDict:
        return {
            "stars": self.stars.to_dict(),
            "index": self.index.to_dict(),
            "fkdr": self.fkdr.to_dict(),
            "kdr": self.kdr.to_dict(),
            "bblr": self.bblr.to_dict(),
            "wlr": self.wlr.to_dict(),
            "winstreak": self.winstreak.to_dict(),
            "kills": self.kills.to_dict(),
            "finals": self.finals.to_dict(),
            "beds": self.beds.to_dict(),
            "wins": self.wins.to_dict(),
            "sessiontime": self.sessiontime.to_dict(),
        }
