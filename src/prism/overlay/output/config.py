from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Self, TypedDict

STARS_RATE_BY_LEVEL = False
STARS_LEVELS = (100.0, 300.0, 500.0, 800.0)
STARS_DECIMALS = 2

FKDR_RATE_BY_LEVEL = True
FKDR_LEVELS = (1.0, 2.0, 4.0, 8.0)
FKDR_DECIMALS = 2

INDEX_RATE_BY_LEVEL = True
INDEX_LEVELS = (100.0, 1_200.0, 8_000.0, 51_200.0)
INDEX_DECIMALS = 0

KDR_RATE_BY_LEVEL = True
KDR_LEVELS = (1.0, 1.5, 2.0, 3.0)
KDR_DECIMALS = 2

BBLR_RATE_BY_LEVEL = True
BBLR_LEVELS = (0.3, 1.0, 2.0, 4.0)
BBLR_DECIMALS = 2

WLR_RATE_BY_LEVEL = True
WLR_LEVELS = (0.3, 1.0, 2.0, 4.0)
WLR_DECIMALS = 2

WINSTREAK_RATE_BY_LEVEL = True
WINSTREAK_LEVELS = (5.0, 15.0, 30.0, 50.0)
WINSTREAK_DECIMALS = 0

KILLS_RATE_BY_LEVEL = True
KILLS_LEVELS = (5_000.0, 10_000.0, 20_000.0, 40_000.0)
KILLS_DECIMALS = 0

FINALS_RATE_BY_LEVEL = True
FINALS_LEVELS = (5_000.0, 10_000.0, 20_000.0, 40_000.0)
FINALS_DECIMALS = 0

BEDS_RATE_BY_LEVEL = True
BEDS_LEVELS = (2_000.0, 5_000.0, 10_000.0, 20_000.0)
BEDS_DECIMALS = 0

WINS_RATE_BY_LEVEL = True
WINS_LEVELS = (1_000.0, 3_000.0, 6_000.0, 10_000.0)
WINS_DECIMALS = 0


class RatingConfigDict(TypedDict):
    """Dict representing a RatingConfig"""

    type: Literal["level_based"]
    rate_by_level: bool
    levels: tuple[float, ...]
    decimals: int


def read_rating_config_dict(
    source: Mapping[str, object],
    default_rate_by_level: bool,
    default_levels: tuple[float, ...],
    default_decimals: int,
) -> tuple[RatingConfigDict, bool]:
    """Read a RatingConfigDict from the source mapping"""
    source_updated = False

    if source.get("type", None) != "level_based":
        source_updated = True

    rate_by_level = source.get("rate_by_level", None)
    if not isinstance(rate_by_level, bool):
        rate_by_level = default_rate_by_level
        source_updated = True

    levels = source.get("levels", None)
    if not isinstance(levels, (list, tuple)) or not all(
        isinstance(el, float) for el in levels
    ):
        levels = default_levels
        source_updated = True

    decimals = source.get("decimals", None)
    if not isinstance(decimals, int) or decimals < 0:
        decimals = default_decimals
        source_updated = True

    return {
        "type": "level_based",
        "rate_by_level": rate_by_level,
        "levels": tuple(levels),
        "decimals": decimals,
    }, source_updated


def safe_read_rating_config_dict(
    source: object,
    default_rate_by_level: bool,
    default_levels: tuple[float, ...],
    default_decimals: int,
) -> tuple[RatingConfigDict, bool]:
    if not isinstance(source, dict):
        source = {}
    return read_rating_config_dict(
        source, default_rate_by_level, default_levels, default_decimals
    )


@dataclass(frozen=True, slots=True)
class RatingConfig:
    """Configuration for how to rate one stat"""

    rate_by_level: bool
    levels: tuple[float, ...]
    decimals: int

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
        )

    def to_dict(self) -> RatingConfigDict:
        return {
            "type": "level_based",
            "rate_by_level": self.rate_by_level,
            "levels": self.levels,
            "decimals": self.decimals,
        }


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


def read_rating_config_collection_dict(
    source: Mapping[str, object]
) -> tuple[RatingConfigCollectionDict, bool]:
    """Read a RatingConfigCollectionDict from the source mapping"""
    any_source_updated = False

    stars, source_updated = safe_read_rating_config_dict(
        source.get("stars", None),
        default_rate_by_level=STARS_RATE_BY_LEVEL,
        default_levels=STARS_LEVELS,
        default_decimals=STARS_DECIMALS,
    )
    any_source_updated |= source_updated

    index, source_updated = safe_read_rating_config_dict(
        source.get("index", None),
        default_rate_by_level=INDEX_RATE_BY_LEVEL,
        default_levels=INDEX_LEVELS,
        default_decimals=INDEX_DECIMALS,
    )
    any_source_updated |= source_updated

    fkdr, source_updated = safe_read_rating_config_dict(
        source.get("fkdr", None),
        default_rate_by_level=FKDR_RATE_BY_LEVEL,
        default_levels=FKDR_LEVELS,
        default_decimals=FKDR_DECIMALS,
    )
    any_source_updated |= source_updated

    kdr, source_updated = safe_read_rating_config_dict(
        source.get("kdr", None),
        default_rate_by_level=KDR_RATE_BY_LEVEL,
        default_levels=KDR_LEVELS,
        default_decimals=KDR_DECIMALS,
    )
    any_source_updated |= source_updated

    bblr, source_updated = safe_read_rating_config_dict(
        source.get("bblr", None),
        default_rate_by_level=BBLR_RATE_BY_LEVEL,
        default_levels=BBLR_LEVELS,
        default_decimals=BBLR_DECIMALS,
    )
    any_source_updated |= source_updated

    wlr, source_updated = safe_read_rating_config_dict(
        source.get("wlr", None),
        default_rate_by_level=WLR_RATE_BY_LEVEL,
        default_levels=WLR_LEVELS,
        default_decimals=WLR_DECIMALS,
    )
    any_source_updated |= source_updated

    winstreak, source_updated = safe_read_rating_config_dict(
        source.get("winstreak", None),
        default_rate_by_level=WINSTREAK_RATE_BY_LEVEL,
        default_levels=WINSTREAK_LEVELS,
        default_decimals=WINSTREAK_DECIMALS,
    )
    any_source_updated |= source_updated

    kills, source_updated = safe_read_rating_config_dict(
        source.get("kills", None),
        default_rate_by_level=KILLS_RATE_BY_LEVEL,
        default_levels=KILLS_LEVELS,
        default_decimals=KILLS_DECIMALS,
    )
    any_source_updated |= source_updated

    finals, source_updated = safe_read_rating_config_dict(
        source.get("finals", None),
        default_rate_by_level=FINALS_RATE_BY_LEVEL,
        default_levels=FINALS_LEVELS,
        default_decimals=FINALS_DECIMALS,
    )
    any_source_updated |= source_updated

    beds, source_updated = safe_read_rating_config_dict(
        source.get("beds", None),
        default_rate_by_level=BEDS_RATE_BY_LEVEL,
        default_levels=BEDS_LEVELS,
        default_decimals=BEDS_DECIMALS,
    )
    any_source_updated |= source_updated

    wins, source_updated = safe_read_rating_config_dict(
        source.get("wins", None),
        default_rate_by_level=WINS_RATE_BY_LEVEL,
        default_levels=WINS_LEVELS,
        default_decimals=WINS_DECIMALS,
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
        }
