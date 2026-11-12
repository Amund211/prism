import pytest

from prism.overlay.team_danger import (
    NICKED_PLAYER_DANGER,
    _player_sort_key,
    _team_order,
    _team_sort_key,
    calculate_lobby_danger,
    calculate_player_danger,
    classify_score_tier,
    is_friendly_player,
    is_player_alive,
    resolve_player_team,
    sample_confidence,
)
from prism.overlay.team_types import (
    DangerTier,
    PlayerDanger,
    TeamColor,
    TeamDangerSummary,
)
from prism.player import (
    KnownPlayer,
    NickedPlayer,
    PendingPlayer,
    Player,
    Stats,
    Tags,
    UnknownPlayer,
)


def make_stats(
    *,
    fkdr: float = 0.0,
    stars: float = 1.0,
    bblr: float = 0.0,
    wlr: float = 0.0,
    winstreak: int | None = None,
    winstreak_accurate: bool = False,
    kills: int = 0,
    finals: int = 0,
    beds: int = 0,
    wins: int = 0,
    kdr: float = 0.0,
) -> Stats:
    return Stats(
        index=stars * fkdr**2,
        fkdr=fkdr,
        kdr=kdr,
        bblr=bblr,
        wlr=wlr,
        winstreak=winstreak,
        winstreak_accurate=winstreak_accurate,
        kills=kills,
        finals=finals,
        beds=beds,
        wins=wins,
    )


def make_known(
    username: str,
    *,
    stars: float = 1.0,
    fkdr: float = 0.0,
    bblr: float = 0.0,
    wlr: float = 0.0,
    winstreak: int | None = None,
    winstreak_accurate: bool = False,
    wins: int = 0,
    finals: int = 0,
    nick: str | None = None,
    sessiontime_seconds: float | None = None,
    tags: Tags | None = None,
) -> KnownPlayer:
    last_login: int | None = None
    last_logout: int | None = None
    received_at: int = 1_000_000

    if sessiontime_seconds is not None:
        last_login = received_at - int(sessiontime_seconds * 1000)
        last_logout = last_login - 1000

    return KnownPlayer(
        dataReceivedAtMs=received_at,
        stats=make_stats(
            fkdr=fkdr,
            stars=stars,
            bblr=bblr,
            wlr=wlr,
            winstreak=winstreak,
            winstreak_accurate=winstreak_accurate,
            wins=wins,
            finals=finals,
        ),
        stars=stars,
        username=username,
        uuid=f"uuid-{username}",
        lastLoginMs=last_login,
        lastLogoutMs=last_logout,
        nick=nick,
        tags=tags,
    )


# ---------------------------------------------------------------------------
# Section 1: sample_confidence & damping
# ---------------------------------------------------------------------------


def test_sample_confidence_damping() -> None:
    # 0 stars, 0 wins, 0 finals -> V = 0, c = 0.25
    p_zero = make_known("Player1", stars=0.0, wins=0, finals=0)
    assert sample_confidence(p_zero) == pytest.approx(0.25)

    # 1 star, 0 wins, 5 finals -> V = 1.0 + 0 + 1.0 = 2.0
    # c = 0.25 + 0.75 * (2/50) = 0.28
    p_alt = make_known("Player2", stars=1.0, wins=0, finals=5)
    assert sample_confidence(p_alt) == pytest.approx(0.28)

    # 50 stars -> V = 50.0 -> c = 1.0
    p_fifty = make_known("Player3", stars=50.0, wins=0, finals=0)
    assert sample_confidence(p_fifty) == pytest.approx(1.0)

    # 200 stars, 100 wins, 50 finals -> V > 50 -> capped at 1.0
    p_established = make_known("Player4", stars=200.0, wins=100, finals=50)
    assert sample_confidence(p_established) == 1.0

    # Negative values clamp to 0.0 -> V = 0, c = 0.25
    p_neg = make_known("Player5", stars=-10.0, wins=-5, finals=-2)
    assert sample_confidence(p_neg) == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Section 2: classify_score_tier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score, expected",
    [
        (-5.0, "low"),
        (0.0, "low"),
        (99.9, "low"),
        (100.0, "medium"),
        (179.9, "medium"),
        (180.0, "high"),
        (299.9, "high"),
        (300.0, "extreme"),
        (750.0, "extreme"),
    ],
)
def test_classify_score_tier(score: float, expected: DangerTier) -> None:
    assert classify_score_tier(score) == expected


# ---------------------------------------------------------------------------
# Section 3: calculate_player_danger
# ---------------------------------------------------------------------------


def test_calculate_player_danger_calibration_profiles() -> None:
    # Casual: 50★, 0.6 FKDR, 0.4 BBLR, 0.3 WLR, 0 WS -> 15.6, low
    p_casual = make_known(
        "Player1",
        stars=50.0,
        fkdr=0.6,
        bblr=0.4,
        wlr=0.3,
        winstreak=0,
    )
    d_casual = calculate_player_danger(p_casual, team="red")
    assert d_casual.danger_score == 15.6
    assert d_casual.status == "known"
    assert d_casual.tier == "low"
    assert d_casual.team == "red"

    # Average: 150★, 1.8 FKDR, 1.0 BBLR, 0.8 WLR, 1 WS (accurate) -> 39.3, low
    p_avg = make_known(
        "Player2",
        stars=150.0,
        fkdr=1.8,
        bblr=1.0,
        wlr=0.8,
        winstreak=1,
        winstreak_accurate=True,
    )
    d_avg = calculate_player_danger(p_avg)
    assert d_avg.danger_score == 39.3
    assert d_avg.status == "known"
    assert d_avg.tier == "low"
    assert d_avg.team is None

    # Solo Carry: 400★, 6.0 FKDR, 2.5 BBLR, 2.5 WLR, 5 WS (accurate) -> 111.0, medium
    p_carry = make_known(
        "Player3",
        stars=400.0,
        fkdr=6.0,
        bblr=2.5,
        wlr=2.5,
        winstreak=5,
        winstreak_accurate=True,
    )
    d_carry = calculate_player_danger(p_carry)
    assert d_carry.danger_score == 111.0
    assert d_carry.status == "known"
    assert d_carry.tier == "medium"

    # Good Party: 200★, 3.5 FKDR, 1.5 BBLR, 1.5 WLR, 2 WS (accurate) -> 65.8, low
    p_good = make_known(
        "Player4",
        stars=200.0,
        fkdr=3.5,
        bblr=1.5,
        wlr=1.5,
        winstreak=2,
        winstreak_accurate=True,
        sessiontime_seconds=700.0,  # >= 10m -> +0.0
    )
    d_good = calculate_player_danger(p_good)
    assert d_good.danger_score == 65.8
    assert d_good.status == "known"
    assert d_good.tier == "low"

    # Nicked Player: baseline 65.0, low
    p_nick = NickedPlayer(nick="Player5")
    d_nick = calculate_player_danger(p_nick, team="blue")
    assert d_nick.danger_score == NICKED_PLAYER_DANGER
    assert d_nick.danger_score == 65.0
    assert d_nick.status == "nicked"
    assert d_nick.tier == "low"
    assert d_nick.team == "blue"

    # Sweat: 600★, 8.0 FKDR, 3.0 BBLR, 3.5 WLR, 15 WS (accurate) -> 157.6, medium
    p_sweat = make_known(
        "Player6",
        stars=600.0,
        fkdr=8.0,
        bblr=3.0,
        wlr=3.5,
        winstreak=15,
        winstreak_accurate=True,
    )
    d_sweat = calculate_player_danger(p_sweat)
    assert d_sweat.danger_score == 157.6
    assert d_sweat.status == "known"
    assert d_sweat.tier == "medium"


def test_calculate_player_danger_caps_and_clamping() -> None:
    # Test upper caps: fkdr=50.0 (capped at 25), bblr=20.0 (capped at 10),
    # wlr=20.0 (capped at 10), stars=3600 (capped at 2500), ws=100 (capped at 50)
    p_capped = make_known(
        "Player1",
        stars=3600.0,
        fkdr=50.0,
        bblr=20.0,
        wlr=20.0,
        winstreak=100,
        winstreak_accurate=True,
    )
    # c = 1.0
    # s_fkdr = 25 * 10 = 250.0
    # s_bblr = 10 * 6 = 60.0
    # s_wlr = 10 * 5 = 50.0
    # s_stars = sqrt(2500) * 0.8 = 50 * 0.8 = 40.0
    # s_ws = 50 * 1.5 = 75.0
    # Total = 250 + 60 + 50 + 40 + 75 = 475.0
    d_capped = calculate_player_danger(p_capped)
    assert d_capped.danger_score == 475.0
    assert d_capped.tier == "extreme"

    # Test lower clamps: negative values
    p_neg = make_known(
        "Player2",
        stars=-10.0,
        fkdr=-5.0,
        bblr=-2.0,
        wlr=-1.0,
        winstreak=-10,
        winstreak_accurate=True,
    )
    d_neg = calculate_player_danger(p_neg)
    assert d_neg.danger_score == 0.0
    assert d_neg.tier == "low"


def test_calculate_player_danger_winstreaks() -> None:
    # winstreak is None -> 0.0
    p_none_ws = make_known("Player1", stars=0.0, winstreak=None)
    assert calculate_player_danger(p_none_ws).danger_score == 0.0

    # winstreak=10, inaccurate (mult 1.0) -> +10.0
    p_inacc = make_known("Player2", stars=0.0, winstreak=10, winstreak_accurate=False)
    assert calculate_player_danger(p_inacc).danger_score == 10.0

    # winstreak=10, accurate (mult 1.5) -> +15.0
    p_acc = make_known("Player3", stars=0.0, winstreak=10, winstreak_accurate=True)
    assert calculate_player_danger(p_acc).danger_score == 15.0


def test_calculate_player_danger_sessiontime() -> None:
    # < 300s -> +8.0
    p_fresh = make_known("Player1", stars=0.0, sessiontime_seconds=120.0)
    assert calculate_player_danger(p_fresh).danger_score == 8.0

    # 300..600s -> +4.0
    p_recent = make_known("Player2", stars=0.0, sessiontime_seconds=450.0)
    assert calculate_player_danger(p_recent).danger_score == 4.0

    # >= 600s -> +0.0
    p_old = make_known("Player3", stars=0.0, sessiontime_seconds=900.0)
    assert calculate_player_danger(p_old).danger_score == 0.0

    # None -> +0.0
    p_none = make_known("Player4", stars=0.0, sessiontime_seconds=None)
    assert calculate_player_danger(p_none).danger_score == 0.0


def test_calculate_player_danger_urchin_tags() -> None:
    # tags is None -> 0.0
    p_notags = make_known("Player1", stars=0.0, tags=None)
    assert calculate_player_danger(p_notags).danger_score == 0.0

    # sniping high (+120), cheating none
    p_sniping_high = make_known(
        "Player2", stars=0.0, tags=Tags(sniping="high", cheating="none")
    )
    assert calculate_player_danger(p_sniping_high).danger_score == 120.0

    # sniping medium (+60), cheating none
    p_sniping_med = make_known(
        "Player3", stars=0.0, tags=Tags(sniping="medium", cheating="none")
    )
    assert calculate_player_danger(p_sniping_med).danger_score == 60.0

    # sniping none, cheating high (+100)
    p_cheating_high = make_known(
        "Player4", stars=0.0, tags=Tags(sniping="none", cheating="high")
    )
    assert calculate_player_danger(p_cheating_high).danger_score == 100.0

    # sniping none, cheating medium (+50)
    p_cheating_med = make_known(
        "Player5", stars=0.0, tags=Tags(sniping="none", cheating="medium")
    )
    assert calculate_player_danger(p_cheating_med).danger_score == 50.0

    # sniping high (+120) + cheating high (+100) -> 220.0
    p_both = make_known(
        "Player6", stars=0.0, tags=Tags(sniping="high", cheating="high")
    )
    assert calculate_player_danger(p_both).danger_score == 220.0


def test_calculate_player_danger_non_known_types() -> None:
    # PendingPlayer
    p_pending = PendingPlayer(username="Player1")
    d_pending = calculate_player_danger(p_pending, team="green")
    assert d_pending.danger_score == 0.0
    assert d_pending.status == "pending"
    assert d_pending.tier == "pending"
    assert d_pending.team == "green"

    # UnknownPlayer
    p_unknown = UnknownPlayer(username="Player2")
    d_unknown = calculate_player_danger(p_unknown, team="yellow")
    assert d_unknown.danger_score == 0.0
    assert d_unknown.status == "unknown"
    assert d_unknown.tier == "unknown"
    assert d_unknown.team == "yellow"


# ---------------------------------------------------------------------------
# Section 4: resolve_player_team, is_player_alive, is_friendly_player
# ---------------------------------------------------------------------------


def test_resolve_player_team() -> None:
    player_teams: dict[str, TeamColor] = {
        "player1": "red",
        "PLAYER2": "blue",
        "nick3": "green",
    }

    # Normal player, exact case match
    p1 = make_known("player1")
    assert resolve_player_team(p1, player_teams) == "red"

    # Normal player, case-insensitive match
    p2 = make_known("player2")
    assert resolve_player_team(p2, player_teams) == "blue"

    # Player with nick: nick matches in player_teams
    p3 = make_known("real3", nick="nick3")
    assert resolve_player_team(p3, player_teams) == "green"

    # Player with nick: username matches, nick does not
    p4 = make_known("player1", nick="other_nick")
    assert resolve_player_team(p4, player_teams) == "red"

    # Player with nick: BOTH nick and username are in mapping ->
    # nick takes precedence (reversed aliases)
    conflict_teams: dict[str, TeamColor] = {"real": "red", "nick": "blue"}
    p_conflict = make_known("real", nick="nick")
    assert resolve_player_team(p_conflict, conflict_teams) == "blue"

    # Player not in mapping
    p_none = make_known("unknown_user")
    assert resolve_player_team(p_none, player_teams) is None

    # Empty player_teams
    assert resolve_player_team(p1, {}) is None


def test_is_player_alive() -> None:
    alive_set = {"Player1", "AmazingNick"}

    p1 = make_known("Player1")
    assert is_player_alive(p1, alive_set) is True

    # Nick is alive, username is not
    p2 = make_known("RealUser", nick="AmazingNick")
    assert is_player_alive(p2, alive_set) is True

    # Neither is alive
    p3 = make_known("DeadPlayer", nick="DeadNick")
    assert is_player_alive(p3, alive_set) is False


def test_is_friendly_player() -> None:
    party = {"PartyMember1", "PartyNick"}

    # In party by username
    p1 = make_known("PartyMember1")
    assert is_friendly_player(p1, party, own_username="Me") is True

    # In party by nick
    p2 = make_known("RealUser", nick="PartyNick")
    assert is_friendly_player(p2, party, own_username="Me") is True

    # Matches own_username
    p3 = make_known("Me")
    assert is_friendly_player(p3, party, own_username="Me") is True

    # Nick matches own_username
    p4 = make_known("RealMe", nick="Me")
    assert is_friendly_player(p4, party, own_username="Me") is True

    # Not friendly
    p5 = make_known("EnemyPlayer", nick="EnemyNick")
    assert is_friendly_player(p5, party, own_username="Me") is False

    # own_username is None and not in party
    assert is_friendly_player(p5, party, own_username=None) is False


# ---------------------------------------------------------------------------
# Section 5: Deterministic Tie-Breaking
# ---------------------------------------------------------------------------


def test_deterministic_player_sort_tie_breaking() -> None:
    # 1. Status ordering: known sorts before unknown, which sorts before pending
    p_known = make_known("PlayerA", stars=50.0)
    d_known = calculate_player_danger(p_known)

    p_unk = UnknownPlayer("PlayerB")
    d_unk = calculate_player_danger(p_unk)

    p_pend = PendingPlayer("PlayerC")
    d_pend = calculate_player_danger(p_pend)

    items: list[tuple[Player, PlayerDanger]] = [
        (p_pend, d_pend),
        (p_unk, d_unk),
        (p_known, d_known),
    ]
    sorted_items = sorted(items, key=_player_sort_key)
    assert [d.username for _, d in sorted_items] == [
        "PlayerA",
        "PlayerB",
        "PlayerC",
    ]

    # 2. Danger score tie-break: higher score first
    p_high = make_known("Player1", stars=200.0)
    d_high = calculate_player_danger(p_high)
    p_low = make_known("Player2", stars=50.0)
    d_low = calculate_player_danger(p_low)
    items_score: list[tuple[Player, PlayerDanger]] = [
        (p_low, d_low),
        (p_high, d_high),
    ]
    assert sorted(items_score, key=_player_sort_key) == [
        (p_high, d_high),
        (p_low, d_low),
    ]

    # 3. Same score, different fkdr: higher fkdr first
    # Note: to get identical score with different fkdr, adjust stars
    # Craft two players with identical score by overriding
    # danger_score directly for test
    d1 = PlayerDanger("User1", 50.0, "known", "low", None)
    p1 = make_known("User1", stars=50.0, fkdr=3.0)
    d2 = PlayerDanger("User2", 50.0, "known", "low", None)
    p2 = make_known("User2", stars=50.0, fkdr=4.0)
    # Higher fkdr (p2) sorts first
    items_fkdr: list[tuple[Player, PlayerDanger]] = [(p1, d1), (p2, d2)]
    assert sorted(items_fkdr, key=_player_sort_key) == [
        (p2, d2),
        (p1, d1),
    ]

    # 4. Same score and fkdr, different stars: higher stars first
    p3 = make_known("User3", stars=100.0, fkdr=3.0)
    d3 = PlayerDanger("User3", 50.0, "known", "low", None)
    items_stars: list[tuple[Player, PlayerDanger]] = [(p1, d1), (p3, d3)]
    assert sorted(items_stars, key=_player_sort_key) == [
        (p3, d3),
        (p1, d1),
    ]

    # 5. Same score, fkdr, stars: username case-insensitive alphabetical
    p_alice = make_known("Alice", stars=50.0, fkdr=3.0)
    d_alice = PlayerDanger("Alice", 50.0, "known", "low", None)
    p_bob = make_known("bob", stars=50.0, fkdr=3.0)
    d_bob = PlayerDanger("bob", 50.0, "known", "low", None)
    items_name: list[tuple[Player, PlayerDanger]] = [
        (p_bob, d_bob),
        (p_alice, d_alice),
    ]
    assert sorted(items_name, key=_player_sort_key) == [
        (p_alice, d_alice),
        (p_bob, d_bob),
    ]

    # 6. Same lower username: exact case ASCII tie-break
    p_upper = make_known("ALICE", stars=50.0, fkdr=3.0)
    d_upper = PlayerDanger("ALICE", 50.0, "known", "low", None)
    items_case: list[tuple[Player, PlayerDanger]] = [
        (p_alice, d_alice),
        (p_upper, d_upper),
    ]
    assert sorted(items_case, key=_player_sort_key) == [
        (p_upper, d_upper),
        (p_alice, d_alice),
    ]


def test_deterministic_team_sort_tie_breaking() -> None:
    # 1. Tier ordering: eligible before pending before unknown
    t_eligible = TeamDangerSummary(
        team="red",
        danger_score=100.0,
        total_player_danger=80.0,
        peak_player_danger=80.0,
        tier="medium",
        alive_count=1,
        known_or_nicked_count=1,
        pending_count=0,
        unknown_count=0,
        top_player="Player1",
        is_own_team=False,
    )
    t_pending = TeamDangerSummary(
        team="blue",
        danger_score=150.0,
        total_player_danger=100.0,
        peak_player_danger=100.0,
        tier="pending",
        alive_count=2,
        known_or_nicked_count=1,
        pending_count=1,
        unknown_count=0,
        top_player="Player2",
        is_own_team=False,
    )
    t_unknown = TeamDangerSummary(
        team="green",
        danger_score=0.0,
        total_player_danger=0.0,
        peak_player_danger=0.0,
        tier="unknown",
        alive_count=1,
        known_or_nicked_count=0,
        pending_count=0,
        unknown_count=1,
        top_player=None,
        is_own_team=False,
    )

    teams = [t_unknown, t_pending, t_eligible]
    sorted_teams = sorted(teams, key=_team_sort_key)
    assert [t.team for t in sorted_teams] == ["red", "blue", "green"]

    # 2. Same tier, danger_score tie-break
    t_red_high = TeamDangerSummary(
        team="red",
        danger_score=200.0,
        total_player_danger=150.0,
        peak_player_danger=100.0,
        tier="high",
        alive_count=2,
        known_or_nicked_count=2,
        pending_count=0,
        unknown_count=0,
        top_player="P1",
        is_own_team=False,
    )
    t_blue_low = TeamDangerSummary(
        team="blue",
        danger_score=150.0,
        total_player_danger=100.0,
        peak_player_danger=100.0,
        tier="medium",
        alive_count=2,
        known_or_nicked_count=2,
        pending_count=0,
        unknown_count=0,
        top_player="P2",
        is_own_team=False,
    )
    assert sorted([t_blue_low, t_red_high], key=_team_sort_key) == [
        t_red_high,
        t_blue_low,
    ]

    # 3. Same score, peak_player_danger tie-break
    t_team_a = TeamDangerSummary(
        team="red",
        danger_score=200.0,
        total_player_danger=150.0,
        peak_player_danger=100.0,
        tier="high",
        alive_count=2,
        known_or_nicked_count=2,
        pending_count=0,
        unknown_count=0,
        top_player="P1",
        is_own_team=False,
    )
    t_team_b = TeamDangerSummary(
        team="blue",
        danger_score=200.0,
        total_player_danger=150.0,
        peak_player_danger=120.0,
        tier="high",
        alive_count=2,
        known_or_nicked_count=2,
        pending_count=0,
        unknown_count=0,
        top_player="P2",
        is_own_team=False,
    )
    assert sorted([t_team_a, t_team_b], key=_team_sort_key) == [
        t_team_b,
        t_team_a,
    ]

    # 4. Same score and peak, alive_count tie-break
    t_team_c = TeamDangerSummary(
        team="red",
        danger_score=200.0,
        total_player_danger=150.0,
        peak_player_danger=100.0,
        tier="high",
        alive_count=3,
        known_or_nicked_count=2,
        pending_count=0,
        unknown_count=1,
        top_player="P1",
        is_own_team=False,
    )
    assert sorted([t_team_a, t_team_c], key=_team_sort_key) == [
        t_team_c,
        t_team_a,
    ]

    # 5. Same score, peak, alive_count: TEAM_ORDER_INDEX (red < blue < green < yellow)
    t_team_red = TeamDangerSummary(
        team="red",
        danger_score=200.0,
        total_player_danger=150.0,
        peak_player_danger=100.0,
        tier="high",
        alive_count=2,
        known_or_nicked_count=2,
        pending_count=0,
        unknown_count=0,
        top_player="P1",
        is_own_team=False,
    )
    t_team_blue = TeamDangerSummary(
        team="blue",
        danger_score=200.0,
        total_player_danger=150.0,
        peak_player_danger=100.0,
        tier="high",
        alive_count=2,
        known_or_nicked_count=2,
        pending_count=0,
        unknown_count=0,
        top_player="P2",
        is_own_team=False,
    )
    assert sorted([t_team_blue, t_team_red], key=_team_sort_key) == [
        t_team_red,
        t_team_blue,
    ]


def test_team_order_helper() -> None:
    assert _team_order(None) == 999
    assert _team_order("red") == 0
    assert _team_order("blue") == 1
    assert _team_order("green") == 2
    assert _team_order("yellow") == 3


# ---------------------------------------------------------------------------
# Section 6: Calibration Rosters (3s & 4s exact calculation)
# ---------------------------------------------------------------------------


def test_calibration_rosters_3s_and_4s() -> None:
    # 1. Casual Queue (3s -> 52.3, 4s -> 67.9, low)
    casual_players_4 = [
        make_known(
            f"Casual{i}",
            stars=50.0,
            fkdr=0.6,
            bblr=0.4,
            wlr=0.3,
            winstreak=0,
        )
        for i in range(4)
    ]
    # 3s
    res_3s = calculate_lobby_danger(
        casual_players_4[:3],
        alive_players={f"Casual{i}" for i in range(3)},
        party_members=set(),
        own_username=None,
        player_teams={f"Casual{i}": "red" for i in range(3)},
    )
    assert res_3s is not None
    assert len(res_3s.enemy_teams) == 1
    t_casual_3s = res_3s.enemy_teams[0]
    assert t_casual_3s.danger_score == 52.3
    assert t_casual_3s.tier == "low"
    assert t_casual_3s.is_eligible_target is True

    # 4s
    res_4s = calculate_lobby_danger(
        casual_players_4,
        alive_players={f"Casual{i}" for i in range(4)},
        party_members=set(),
        own_username=None,
        player_teams={f"Casual{i}": "red" for i in range(4)},
    )
    assert res_4s is not None
    t_casual_4s = res_4s.enemy_teams[0]
    assert t_casual_4s.danger_score == 67.9
    assert t_casual_4s.tier == "low"

    # 2. Average / Decent (3s -> 131.7, 4s -> 171.0, medium)
    avg_players_4 = [
        make_known(
            f"Avg{i}",
            stars=150.0,
            fkdr=1.8,
            bblr=1.0,
            wlr=0.8,
            winstreak=1,
            winstreak_accurate=True,
        )
        for i in range(4)
    ]
    res_avg_3s = calculate_lobby_danger(
        avg_players_4[:3],
        alive_players={f"Avg{i}" for i in range(3)},
        party_members=set(),
        own_username=None,
        player_teams={f"Avg{i}": "blue" for i in range(3)},
    )
    assert res_avg_3s is not None
    assert res_avg_3s.enemy_teams[0].danger_score == 131.7
    assert res_avg_3s.enemy_teams[0].tier == "medium"

    res_avg_4s = calculate_lobby_danger(
        avg_players_4,
        alive_players={f"Avg{i}" for i in range(4)},
        party_members=set(),
        own_username=None,
        player_teams={f"Avg{i}": "blue" for i in range(4)},
    )
    assert res_avg_4s is not None
    assert res_avg_4s.enemy_teams[0].danger_score == 171.0
    assert res_avg_4s.enemy_teams[0].tier == "medium"

    # 3. Solo Carry + Casuals (3s -> 181.1, 4s -> 196.7, high)
    carry = make_known(
        "Carry",
        stars=400.0,
        fkdr=6.0,
        bblr=2.5,
        wlr=2.5,
        winstreak=5,
        winstreak_accurate=True,
    )
    carry_roster_3 = [carry, casual_players_4[0], casual_players_4[1]]
    res_carry_3s = calculate_lobby_danger(
        carry_roster_3,
        alive_players={"Carry", "Casual0", "Casual1"},
        party_members=set(),
        own_username=None,
        player_teams={p.username: "green" for p in carry_roster_3},
    )
    assert res_carry_3s is not None
    assert res_carry_3s.enemy_teams[0].danger_score == 181.1
    assert res_carry_3s.enemy_teams[0].tier == "high"
    assert res_carry_3s.enemy_teams[0].top_player == "Carry"

    carry_roster_4 = [carry] + casual_players_4[:3]
    res_carry_4s = calculate_lobby_danger(
        carry_roster_4,
        alive_players={"Carry", "Casual0", "Casual1", "Casual2"},
        party_members=set(),
        own_username=None,
        player_teams={p.username: "green" for p in carry_roster_4},
    )
    assert res_carry_4s is not None
    assert res_carry_4s.enemy_teams[0].danger_score == 196.7
    assert res_carry_4s.enemy_teams[0].tier == "high"

    # 4. Good Party / All Nicks (3s -> 250.4 high, 4s -> 331.2 extreme)
    good_players_4 = [
        make_known(
            f"Good{i}",
            stars=200.0,
            fkdr=3.5,
            bblr=1.5,
            wlr=1.5,
            winstreak=2,
            winstreak_accurate=True,
            sessiontime_seconds=700.0,
        )
        for i in range(4)
    ]
    res_good_3s = calculate_lobby_danger(
        good_players_4[:3],
        alive_players={f"Good{i}" for i in range(3)},
        party_members=set(),
        own_username=None,
        player_teams={f"Good{i}": "yellow" for i in range(3)},
    )
    assert res_good_3s is not None
    assert res_good_3s.enemy_teams[0].danger_score == 250.4
    assert res_good_3s.enemy_teams[0].tier == "high"

    res_good_4s = calculate_lobby_danger(
        good_players_4,
        alive_players={f"Good{i}" for i in range(4)},
        party_members=set(),
        own_username=None,
        player_teams={f"Good{i}": "yellow" for i in range(4)},
    )
    assert res_good_4s is not None
    assert res_good_4s.enemy_teams[0].danger_score == 331.2
    assert res_good_4s.enemy_teams[0].tier == "extreme"

    # 4s All Nicks: 4x 65.0 = 260.0 + 0.35*65 (22.75) + 3*15 (45.0)
    # = 327.75 -> 327.8 (extreme)
    all_nicks_4 = [NickedPlayer(f"Nick{i}") for i in range(4)]
    res_nicks_4s = calculate_lobby_danger(
        all_nicks_4,
        alive_players={f"Nick{i}" for i in range(4)},
        party_members=set(),
        own_username=None,
        player_teams={f"Nick{i}": "yellow" for i in range(4)},
    )
    assert res_nicks_4s is not None
    assert res_nicks_4s.enemy_teams[0].danger_score == 327.8
    assert res_nicks_4s.enemy_teams[0].tier == "extreme"

    # 5. Sweat Winstreak Stack (3s -> 558.0 extreme, 4s -> 730.6 extreme)
    sweat_players_4 = [
        make_known(
            f"Sweat{i}",
            stars=600.0,
            fkdr=8.0,
            bblr=3.0,
            wlr=3.5,
            winstreak=15,
            winstreak_accurate=True,
        )
        for i in range(4)
    ]
    res_sweat_3s = calculate_lobby_danger(
        sweat_players_4[:3],
        alive_players={f"Sweat{i}" for i in range(3)},
        party_members=set(),
        own_username=None,
        player_teams={f"Sweat{i}": "red" for i in range(3)},
    )
    assert res_sweat_3s is not None
    assert res_sweat_3s.enemy_teams[0].danger_score == 558.0
    assert res_sweat_3s.enemy_teams[0].tier == "extreme"

    res_sweat_4s = calculate_lobby_danger(
        sweat_players_4,
        alive_players={f"Sweat{i}" for i in range(4)},
        party_members=set(),
        own_username=None,
        player_teams={f"Sweat{i}": "red" for i in range(4)},
    )
    assert res_sweat_4s is not None
    assert res_sweat_4s.enemy_teams[0].danger_score == 730.6
    assert res_sweat_4s.enemy_teams[0].tier == "extreme"

    # 6. 4x Unknown (API Error) -> 0.0, unknown tier, is_eligible_target False
    unknown_players_4 = [UnknownPlayer(f"Err{i}") for i in range(4)]
    res_unk_4s = calculate_lobby_danger(
        unknown_players_4,
        alive_players={f"Err{i}" for i in range(4)},
        party_members=set(),
        own_username=None,
        player_teams={f"Err{i}": "blue" for i in range(4)},
    )
    assert res_unk_4s is not None
    assert res_unk_4s.enemy_teams[0].danger_score == 0.0
    assert res_unk_4s.enemy_teams[0].tier == "unknown"
    assert res_unk_4s.enemy_teams[0].top_player is None
    assert res_unk_4s.enemy_teams[0].is_eligible_target is False
    assert res_unk_4s.priority_target is None


# ---------------------------------------------------------------------------
# Section 7: calculate_lobby_danger behavior & rules
# ---------------------------------------------------------------------------


def test_calculate_lobby_danger_early_returns() -> None:
    p1 = make_known("Player1")
    # is_duel is True
    assert (
        calculate_lobby_danger(
            [p1],
            alive_players={"Player1"},
            party_members=set(),
            own_username=None,
            player_teams={"Player1": "red"},
            is_duel=True,
        )
        is None
    )

    # lobby_size > 16
    assert (
        calculate_lobby_danger(
            [p1],
            alive_players={"Player1"},
            party_members=set(),
            own_username=None,
            player_teams={"Player1": "red"},
            lobby_size=17,
        )
        is None
    )

    # 0 alive players
    assert (
        calculate_lobby_danger(
            [p1],
            alive_players=set(),
            party_members=set(),
            own_username=None,
            player_teams={"Player1": "red"},
        )
        is None
    )

    # Only friendly players alive (0 alive enemy players)
    assert (
        calculate_lobby_danger(
            [p1],
            alive_players={"Player1"},
            party_members={"Player1"},
            own_username="Player1",
            player_teams={"Player1": "red"},
        )
        is None
    )


def test_calculate_lobby_danger_own_team_resolution() -> None:
    me = make_known("Me")
    friend = make_known("Friend")
    random_teammate = make_known("RandomTeammate")
    enemy = make_known("Enemy")

    players = [me, friend, random_teammate, enemy]
    alive = {"Me", "Friend", "RandomTeammate", "Enemy"}

    # 1. Matching own_username preferred for own_team_color
    res = calculate_lobby_danger(
        players,
        alive_players=alive,
        party_members={"Friend"},
        own_username="Me",
        player_teams={
            "Me": "red",
            "Friend": "blue",
            "RandomTeammate": "red",
            "Enemy": "green",
        },
    )
    assert res is not None
    assert res.own_team is not None
    assert res.own_team.team == "red"
    assert res.own_team.alive_count == 2  # Me and RandomTeammate
    assert len(res.enemy_teams) == 1
    assert res.enemy_teams[0].team == "green"

    # 2. own_username not mapped, falls back to friendly player's
    # lowest TEAM_ORDER_INDEX
    res_fallback = calculate_lobby_danger(
        players,
        alive_players=alive,
        party_members={"Friend"},
        own_username=None,
        player_teams={
            "Friend": "blue",
            "RandomTeammate": "blue",
            "Enemy": "green",
        },
    )
    assert res_fallback is not None
    assert res_fallback.own_team is not None
    assert res_fallback.own_team.team == "blue"

    # 3. own_username mapped directly in player_teams when not in players list
    res_direct_own = calculate_lobby_danger(
        [enemy],
        alive_players={"Enemy"},
        party_members=set(),
        own_username="Me",
        player_teams={"me": "yellow", "Enemy": "red"},
    )
    assert res_direct_own is not None
    assert res_direct_own.own_team is None  # yellow has 0 alive players in players
    assert len(res_direct_own.enemy_teams) == 1
    assert res_direct_own.enemy_teams[0].team == "red"

    # 4. party_members mapped directly in player_teams fallback
    res_direct_party = calculate_lobby_danger(
        [enemy],
        alive_players={"Enemy"},
        party_members={"AbsentFriend"},
        own_username=None,
        player_teams={"absentfriend": "blue", "Enemy": "red"},
    )
    assert res_direct_party is not None
    assert len(res_direct_party.enemy_teams) == 1
    assert res_direct_party.enemy_teams[0].team == "red"

    # 5. Multiple friendly players with different teams, picks lowest index
    friend1 = make_known("Friend1")
    friend2 = make_known("Friend2")
    res_multi_friends = calculate_lobby_danger(
        [friend1, friend2, enemy],
        alive_players={"Friend1", "Friend2", "Enemy"},
        party_members={"Friend1", "Friend2"},
        own_username=None,
        player_teams={
            "Friend1": "yellow",  # index 3
            "Friend2": "blue",  # index 1
            "Enemy": "red",
        },
    )
    assert res_multi_friends is not None
    assert res_multi_friends.own_team is not None
    assert res_multi_friends.own_team.team == "blue"


def test_calculate_lobby_danger_dead_players_filtered() -> None:
    # Dead players must not contribute to danger scores or alive counts
    alive_enemy = make_known(
        "AliveEnemy",
        stars=50.0,
        fkdr=0.6,
        bblr=0.4,
        wlr=0.3,
        winstreak=0,
    )
    dead_enemy = make_known(
        "DeadEnemy",
        stars=600.0,
        fkdr=8.0,
        bblr=3.0,
        wlr=3.5,
        winstreak=15,
        winstreak_accurate=True,
    )
    players = [alive_enemy, dead_enemy]
    alive = {"AliveEnemy"}  # DeadEnemy is dead

    res = calculate_lobby_danger(
        players,
        alive_players=alive,
        party_members=set(),
        own_username=None,
        player_teams={"AliveEnemy": "red", "DeadEnemy": "red"},
    )
    assert res is not None
    assert len(res.enemy_teams) == 1
    team_red = res.enemy_teams[0]
    assert team_red.alive_count == 1
    assert team_red.danger_score == 21.1  # 15.6 + 0.35*15.6 = 21.06 -> 21.1


def test_calculate_lobby_danger_pending_enemy_suppression() -> None:
    # If any assigned enemy team has pending_count > 0, priority_target must be None!
    p_known = make_known("KnownEnemy", stars=200.0, fkdr=3.5)
    p_pend = PendingPlayer("PendingEnemy")

    res = calculate_lobby_danger(
        [p_known, p_pend],
        alive_players={"KnownEnemy", "PendingEnemy"},
        party_members=set(),
        own_username=None,
        player_teams={"KnownEnemy": "red", "PendingEnemy": "blue"},
    )
    assert res is not None
    assert res.priority_target is None
    assert res.pending_enemy_count == 1

    # Team with pending player has tier="pending" and is not eligible
    blue_team = next(t for t in res.enemy_teams if t.team == "blue")
    assert blue_team.tier == "pending"
    assert blue_team.is_eligible_target is False


def test_calculate_lobby_danger_unassigned_enemies() -> None:
    p_unassigned_known = make_known("UnassignedKnown", stars=50.0, fkdr=1.0)
    p_unassigned_pend = PendingPlayer("UnassignedPend")
    p_unassigned_unk = UnknownPlayer("UnassignedUnk")
    p_assigned_known = make_known("AssignedKnown", stars=50.0, fkdr=1.0)
    p_friendly_unassigned = make_known("FriendlyUnassigned")

    players: list[Player] = [
        p_unassigned_known,
        p_unassigned_pend,
        p_unassigned_unk,
        p_assigned_known,
        p_friendly_unassigned,
    ]
    alive = {p.username for p in players}

    res = calculate_lobby_danger(
        players,
        alive_players=alive,
        party_members={"FriendlyUnassigned"},
        own_username=None,
        player_teams={"AssignedKnown": "red"},
    )
    assert res is not None
    assert len(res.enemy_teams) == 1
    assert len(res.unassigned_enemies) == 3

    # Check unassigned enemies are sorted deterministically: known -> unknown -> pending
    assert [d.username for d in res.unassigned_enemies] == [
        "UnassignedKnown",
        "UnassignedUnk",
        "UnassignedPend",
    ]
    assert res.pending_enemy_count == 1
    assert res.unknown_enemy_count == 1


def test_calculate_lobby_danger_phase_transitions() -> None:
    p1 = make_known("Enemy1")
    players = [p1]
    alive = {"Enemy1"}
    teams: dict[str, TeamColor] = {"Enemy1": "red"}

    # 1. None time, no finals -> opening
    res_none = calculate_lobby_danger(
        players,
        alive_players=alive,
        party_members=set(),
        own_username=None,
        player_teams=teams,
        time_in_game=None,
        any_final_kills=False,
    )
    assert res_none is not None
    assert res_none.phase == "opening"

    # 2. time_in_game <= 90.0, no finals -> opening
    res_90 = calculate_lobby_danger(
        players,
        alive_players=alive,
        party_members=set(),
        own_username=None,
        player_teams=teams,
        time_in_game=90.0,
        any_final_kills=False,
    )
    assert res_90 is not None
    assert res_90.phase == "opening"

    # 3. time_in_game > 90.0 -> midgame
    res_91 = calculate_lobby_danger(
        players,
        alive_players=alive,
        party_members=set(),
        own_username=None,
        player_teams=teams,
        time_in_game=90.1,
        any_final_kills=False,
    )
    assert res_91 is not None
    assert res_91.phase == "midgame"

    # 4. any_final_kills=True (even if time <= 90) -> midgame
    res_final = calculate_lobby_danger(
        players,
        alive_players=alive,
        party_members=set(),
        own_username=None,
        player_teams=teams,
        time_in_game=10.0,
        any_final_kills=True,
    )
    assert res_final is not None
    assert res_final.phase == "midgame"


def test_calculate_lobby_danger_synergy_bonus() -> None:
    # 2 players with score >= 50.0 -> SynergyBonus = 15.0 * (2 - 1) = 15.0
    p1 = make_known(
        "P1",
        stars=200.0,
        fkdr=3.5,
        bblr=1.5,
        wlr=1.5,
        winstreak=2,
        winstreak_accurate=True,
    )  # score 65.8 >= 50.0
    p2 = make_known(
        "P2",
        stars=200.0,
        fkdr=3.5,
        bblr=1.5,
        wlr=1.5,
        winstreak=2,
        winstreak_accurate=True,
    )  # score 65.8 >= 50.0

    res = calculate_lobby_danger(
        [p1, p2],
        alive_players={"P1", "P2"},
        party_members=set(),
        own_username=None,
        player_teams={"P1": "red", "P2": "red"},
    )
    assert res is not None
    assert len(res.enemy_teams) == 1
    # total = 65.8 + 65.8 = 131.6
    # peak = 65.8 -> 0.35 * 65.8 = 23.03
    # synergy = 15.0
    # D(T) = round(131.6 + 23.03 + 15.0, 1) = round(169.63, 1) = 169.6
    assert res.enemy_teams[0].danger_score == 169.6
