"""Synthetic Player fixtures used by the settings-page preview.

Stats are tuned so each KnownPlayer lands in a different rating tier under the
default configs in `prism.overlay.output.config` — the user sees all five
GUI_COLORS at once when the preview is open with default thresholds.

Numbers are kept round but match the rough shapes seen on real Hypixel
BedWars accounts (KDR rarely tracks skill — most accounts sit between 0.6
and 1.3 across all tiers; FKDR / BBLR / WLR / index do most of the colour
differentiation). Hidden winstreaks are common at every tier.
"""

from prism.player import KnownPlayer, NickedPlayer, Player, Stats, Tags

_DATA_RECEIVED_MS = 1_700_000_000_000  # Fixed for cache stability + sessiontime math


def _player(
    *,
    username: str,
    stars: float,
    index: float,
    fkdr: float,
    kdr: float,
    bblr: float,
    wlr: float,
    winstreak: int | None,
    kills: int,
    finals: int,
    beds: int,
    wins: int,
    sessiontime_seconds: int | None,
    nick: str | None = None,
    tags: Tags | None = None,
) -> KnownPlayer:
    # sessiontime_seconds=None ⇒ render the cell as `-` (hidden / offline).
    # KnownPlayer.sessiontime_seconds returns None when lastLoginMs is None.
    last_login_ms = (
        None
        if sessiontime_seconds is None
        else _DATA_RECEIVED_MS - sessiontime_seconds * 1000
    )
    return KnownPlayer(
        dataReceivedAtMs=_DATA_RECEIVED_MS,
        lastLoginMs=last_login_ms,
        lastLogoutMs=0,
        username=username,
        # Deterministic uuids derived from username, distinct enough for any
        # preview-internal use; never sent over the network.
        uuid=f"00000000-0000-0000-0000-{abs(hash(username)) % 10**12:012d}",
        stars=stars,
        nick=nick,
        tags=tags,
        stats=Stats(
            index=index,
            fkdr=fkdr,
            kdr=kdr,
            bblr=bblr,
            wlr=wlr,
            winstreak=winstreak,
            winstreak_accurate=winstreak is not None,
            kills=kills,
            finals=finals,
            beds=beds,
            wins=wins,
        ),
    )


PLACEHOLDER_PLAYERS: tuple[Player, ...] = (
    # Tier 0 ("Meh", gray) — beginner; under every first threshold.
    _player(
        username="Rookie",
        stars=12.0,
        index=6.0,
        fkdr=0.7,
        kdr=0.4,
        bblr=0.4,
        wlr=0.5,
        winstreak=None,  # hidden ws — common on new accounts
        kills=500,
        finals=200,
        beds=80,
        wins=100,
        sessiontime_seconds=600,
    ),
    # Tier 1 ("Decent", white) — casual.
    _player(
        username="Regular",
        stars=80.0,
        index=180.0,
        fkdr=1.5,
        kdr=1.3,
        bblr=0.8,
        wlr=1.0,
        winstreak=2,
        kills=4_000,
        finals=2_000,
        beds=800,
        wins=800,
        sessiontime_seconds=1800,
    ),
    # Tier 2 ("Good", yellow) — active player. Has a nick → demos the edit
    # button enabled.
    _player(
        username="Tryhard",
        stars=200.0,
        index=1_800.0,
        fkdr=3.0,
        kdr=0.7,
        bblr=1.5,
        wlr=1.5,
        winstreak=5,
        kills=12_000,
        finals=8_000,
        beds=3_000,
        wins=2_000,
        sessiontime_seconds=900,
        nick="Martinez2003",
    ),
    # Tier 3 ("Scary", orange) — experienced.
    _player(
        username="Veteran",
        stars=600.0,
        index=21_600.0,
        fkdr=6.0,
        kdr=0.9,
        bblr=2.5,
        wlr=2.5,
        winstreak=None,  # hidden ws — older account
        kills=20_000,
        finals=20_000,
        beds=6_500,
        wins=5_500,
        sessiontime_seconds=7_200,  # ~2 hr — long grind session
    ),
    # Tier 4 ("Top", red) — top-tier sweat. Tagged as a cheater so the tags
    # column auto-appears in the preview.
    _player(
        username="Sweat",
        stars=1_500.0,
        index=216_000.0,
        fkdr=12.0,
        kdr=1.1,
        bblr=4.0,
        wlr=4.0,
        winstreak=None,
        kills=70_000,
        finals=80_000,
        beds=25_000,
        wins=18_000,
        sessiontime_seconds=None,  # hidden — top players often don't broadcast presence
        tags=Tags(sniping="none", cheating="medium"),
    ),
    # Low-stat account but slightly elevated KDR — the typical sniper-alt
    # profile. Tagged as a sniper.
    _player(
        username="Sniper",
        stars=30.0,
        index=20.0,
        fkdr=0.8,
        kdr=1.5,
        bblr=0.3,
        wlr=0.5,
        winstreak=None,
        kills=900,
        finals=300,
        beds=60,
        wins=70,
        sessiontime_seconds=200,
        tags=Tags(sniping="high", cheating="none"),
    ),
    # Demonstrates the "nick" cell rendering and edit-button enabled.
    NickedPlayer(nick="MysteryGuy"),
)
