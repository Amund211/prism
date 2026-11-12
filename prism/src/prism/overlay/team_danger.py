import math
from collections.abc import Iterable, Mapping, Sequence, Set
from typing import Literal, assert_never

from prism.overlay.team_types import (
    ALL_TEAM_COLORS,
    TEAM_ORDER_INDEX,
    DangerTier,
    LobbyDangerSummary,
    PlayerDanger,
    RecommendationPhase,
    TeamColor,
    TeamDangerSummary,
)
from prism.player import KnownPlayer, NickedPlayer, PendingPlayer, Player, UnknownPlayer

NICKED_PLAYER_DANGER: float = 65.0


def sample_confidence(player: KnownPlayer) -> float:
    """Compute sample-size confidence damping factor in [0.25, 1.0]."""
    v = (
        max(player.stars, 0.0)
        + 0.5 * max(player.stats.wins, 0)
        + 0.2 * max(player.stats.finals, 0)
    )
    return min(1.0, 0.25 + 0.75 * (v / 50.0))


def classify_score_tier(
    score: float,
) -> Literal["low", "medium", "high", "extreme"]:
    """Classify a numeric danger score into a danger tier."""
    if score < 100.0:
        return "low"
    if score < 180.0:
        return "medium"
    if score < 300.0:
        return "high"
    return "extreme"


def calculate_player_danger(
    player: Player,
    team: TeamColor | None = None,
) -> PlayerDanger:
    """Calculate the danger score and tier for an individual player."""
    match player:
        case KnownPlayer():
            c = sample_confidence(player)
            s_fkdr = c * min(max(player.stats.fkdr, 0.0), 25.0) * 10.0
            s_bblr = c * min(max(player.stats.bblr, 0.0), 10.0) * 6.0
            s_wlr = c * min(max(player.stats.wlr, 0.0), 10.0) * 5.0
            s_stars = math.sqrt(min(max(player.stars, 0.0), 2500.0)) * 0.8

            if player.stats.winstreak is not None:
                mult = 1.5 if player.stats.winstreak_accurate else 1.0
                s_ws = min(max(player.stats.winstreak, 0), 50) * mult
            else:
                s_ws = 0.0

            if (
                player.sessiontime_seconds is not None
                and player.sessiontime_seconds < 300.0
            ):
                s_session = 8.0
            elif (
                player.sessiontime_seconds is not None
                and player.sessiontime_seconds < 600.0
            ):
                s_session = 4.0
            else:
                s_session = 0.0

            s_tags = 0.0
            if player.tags is not None:
                if player.tags.sniping == "high":
                    s_tags += 120.0
                elif player.tags.sniping == "medium":
                    s_tags += 60.0

                if player.tags.cheating == "high":
                    s_tags += 100.0
                elif player.tags.cheating == "medium":
                    s_tags += 50.0

            score = round(
                s_fkdr + s_bblr + s_wlr + s_stars + s_ws + s_session + s_tags,
                1,
            )
            return PlayerDanger(
                username=player.username,
                danger_score=score,
                status="known",
                tier=classify_score_tier(score),
                team=team,
            )
        case NickedPlayer():
            return PlayerDanger(
                username=player.username,
                danger_score=NICKED_PLAYER_DANGER,
                status="nicked",
                tier=classify_score_tier(NICKED_PLAYER_DANGER),
                team=team,
            )
        case PendingPlayer():
            return PlayerDanger(
                username=player.username,
                danger_score=0.0,
                status="pending",
                tier="pending",
                team=team,
            )
        case UnknownPlayer():
            return PlayerDanger(
                username=player.username,
                danger_score=0.0,
                status="unknown",
                tier="unknown",
                team=team,
            )
        case _ as unreachable:  # pragma: no cover
            assert_never(unreachable)


def resolve_player_team(
    player: Player,
    player_teams: Mapping[str, TeamColor],
) -> TeamColor | None:
    """Resolve a player's team color from player_teams mapping.

    Checks reversed(player.aliases) (nick first, then username)
    case-insensitively against player_teams keys.
    """
    lower_teams = {k.lower(): v for k, v in player_teams.items()}
    for alias in reversed(player.aliases):
        team = lower_teams.get(alias.lower())
        if team is not None:
            return team
    return None


def is_player_alive(player: Player, alive_players: Set[str]) -> bool:
    """Return True if any alias of player is in alive_players."""
    return any(alias in alive_players for alias in player.aliases)


def is_friendly_player(
    player: Player,
    party_members: Set[str],
    own_username: str | None,
) -> bool:
    """Return True if player is a party member or matches own_username."""
    return any(
        alias in party_members or alias == own_username for alias in player.aliases
    )


def _team_order(color: TeamColor | None) -> int:
    if color is None:
        return 999
    return TEAM_ORDER_INDEX[color]


def _player_sort_key(
    item: tuple[Player, PlayerDanger],
) -> tuple[bool, bool, float, float, float, str, str]:
    player, danger = item
    if isinstance(player, KnownPlayer):
        fkdr = player.stats.fkdr
        stars = player.stars
    else:
        fkdr = 0.0
        stars = 0.0
    return (
        danger.status == "pending",
        danger.status == "unknown",
        -danger.danger_score,
        -fkdr,
        -stars,
        danger.username.lower(),
        danger.username,
    )


def _team_sort_key(
    summary: TeamDangerSummary,
) -> tuple[bool, bool, float, float, float, int]:
    return (
        summary.tier == "unknown",
        summary.tier == "pending",
        -summary.danger_score,
        -summary.peak_player_danger,
        -summary.alive_count,
        TEAM_ORDER_INDEX[summary.team],
    )


def calculate_lobby_danger(
    players: Sequence[Player],
    *,
    alive_players: Set[str],
    party_members: Set[str],
    own_username: str | None,
    player_teams: Mapping[str, TeamColor],
    time_in_game: float | None = None,
    any_final_kills: bool = False,
    is_duel: bool = False,
    lobby_size: int = 0,
) -> LobbyDangerSummary | None:
    """Calculate the aggregate lobby danger summary across all teams."""
    if is_duel or lobby_size > 16:
        return None

    # Filter players to alive only
    alive = [p for p in players if is_player_alive(p, alive_players)]

    # Resolve own team color:
    # Prefer friendly player matching own_username, else lowest TEAM_ORDER_INDEX
    own_team_color: TeamColor | None = None

    if own_username is not None:
        for p in players:
            if any(alias == own_username for alias in p.aliases):
                resolved = resolve_player_team(p, player_teams)
                if resolved is not None:
                    own_team_color = resolved
                    break

        if own_team_color is None:
            lower_teams = {k.lower(): v for k, v in player_teams.items()}
            own_team_color = lower_teams.get(own_username.lower())

    if own_team_color is None:
        friendly_candidates: list[TeamColor] = []
        for p in players:
            if is_friendly_player(p, party_members, own_username):
                resolved = resolve_player_team(p, player_teams)
                if resolved is not None:
                    friendly_candidates.append(resolved)
        if friendly_candidates:
            own_team_color = min(friendly_candidates, key=_team_order)

    if own_team_color is None and party_members:
        lower_teams = {k.lower(): v for k, v in player_teams.items()}
        party_teams: list[TeamColor] = [
            lower_teams[m.lower()] for m in party_members if m.lower() in lower_teams
        ]
        if party_teams:
            own_team_color = min(party_teams, key=_team_order)

    # Alive non-friendly players:
    alive_enemies: list[Player] = []
    for p in alive:
        is_friendly = is_friendly_player(p, party_members, own_username)
        team = resolve_player_team(p, player_teams)
        if not is_friendly and (own_team_color is None or team != own_team_color):
            alive_enemies.append(p)

    if not alive_enemies:
        return None

    # Group alive players by team (and unassigned enemies)
    team_alive_map: dict[TeamColor, list[tuple[Player, PlayerDanger]]] = {
        color: [] for color in ALL_TEAM_COLORS
    }
    unassigned_enemies_items: list[tuple[Player, PlayerDanger]] = []

    for p in alive:
        team = resolve_player_team(p, player_teams)
        is_friendly = is_friendly_player(p, party_members, own_username)
        is_on_own_team = is_friendly or (
            own_team_color is not None and team == own_team_color
        )

        danger = calculate_player_danger(p, team=team)

        if team is not None:
            if team == own_team_color or not is_friendly:
                team_alive_map[team].append((p, danger))
        elif not is_on_own_team:
            unassigned_enemies_items.append((p, danger))

    # Build TeamDangerSummary for each team with >= 1 alive player
    enemy_summaries: list[TeamDangerSummary] = []
    own_team_summary: TeamDangerSummary | None = None

    for color in ALL_TEAM_COLORS:
        team_alive = team_alive_map[color]
        if not team_alive:
            continue

        alive_count = len(team_alive)
        known_or_nicked = [
            (p, d) for p, d in team_alive if d.status in ("known", "nicked")
        ]
        known_or_nicked_count = len(known_or_nicked)
        pending_count = sum(1 for p, d in team_alive if d.status == "pending")
        unknown_count = sum(1 for p, d in team_alive if d.status == "unknown")
        is_own = color == own_team_color

        if known_or_nicked_count == 0:
            total_player_danger = 0.0
            peak_player_danger = 0.0
            danger_score = 0.0
            top_player: str | None = None
        else:
            total_player_danger = round(
                sum(d.danger_score for p, d in known_or_nicked), 1
            )
            peak_player_danger = max(d.danger_score for p, d in known_or_nicked)
            synergy_count = sum(1 for p, d in known_or_nicked if d.danger_score >= 50.0)
            synergy_bonus = 15.0 * max(0, synergy_count - 1)
            danger_score = round(
                total_player_danger + 0.35 * peak_player_danger + synergy_bonus + 1e-9,
                1,
            )
            sorted_known = sorted(known_or_nicked, key=_player_sort_key)
            top_player = sorted_known[0][1].username

        if pending_count > 0:
            tier: DangerTier = "pending"
        elif known_or_nicked_count == 0:
            tier = "unknown"
        else:
            tier = classify_score_tier(danger_score)

        summary = TeamDangerSummary(
            team=color,
            danger_score=danger_score,
            total_player_danger=total_player_danger,
            peak_player_danger=peak_player_danger,
            tier=tier,
            alive_count=alive_count,
            known_or_nicked_count=known_or_nicked_count,
            pending_count=pending_count,
            unknown_count=unknown_count,
            top_player=top_player,
            is_own_team=is_own,
        )

        if is_own:
            own_team_summary = summary
        else:
            enemy_summaries.append(summary)

    # Sort enemy teams deterministically
    sorted_enemy_teams = tuple(sorted(enemy_summaries, key=_team_sort_key))

    # Sort unassigned enemies deterministically
    sorted_unassigned_enemies = tuple(
        d for p, d in sorted(unassigned_enemies_items, key=_player_sort_key)
    )

    # Priority target:
    # First team in enemy_teams where team.is_eligible_target is True,
    # ONLY IF no assigned enemy team has pending_count > 0.
    if any(t.pending_count > 0 for t in sorted_enemy_teams):
        priority_target: TeamDangerSummary | None = None
    else:
        priority_target = next(
            (t for t in sorted_enemy_teams if t.is_eligible_target), None
        )

    # Pending and unknown enemy counts across assigned and unassigned
    pending_enemy_count = sum(t.pending_count for t in sorted_enemy_teams) + sum(
        1 for d in sorted_unassigned_enemies if d.status == "pending"
    )

    unknown_enemy_count = sum(t.unknown_count for t in sorted_enemy_teams) + sum(
        1 for d in sorted_unassigned_enemies if d.status == "unknown"
    )

    # Phase: midgame if any_final_kills or
    # (time_in_game is not None and time_in_game > 90.0)
    phase: RecommendationPhase = (
        "midgame"
        if any_final_kills or (time_in_game is not None and time_in_game > 90.0)
        else "opening"
    )

    return LobbyDangerSummary(
        phase=phase,
        enemy_teams=sorted_enemy_teams,
        own_team=own_team_summary,
        priority_target=priority_target,
        unassigned_enemies=sorted_unassigned_enemies,
        pending_enemy_count=pending_enemy_count,
        unknown_enemy_count=unknown_enemy_count,
    )


def get_top_unassigned_threat_username(
    players: Iterable[Player],
    *,
    alive_players: Set[str],
    party_members: Set[str],
    own_username: str | None,
    player_teams: Mapping[str, TeamColor],
) -> str | None:
    """Return the username of the highest danger unassigned alive enemy."""
    unassigned: list[tuple[Player, PlayerDanger]] = []
    for p in players:
        if not is_player_alive(p, alive_players):
            continue
        if is_friendly_player(p, party_members, own_username):
            continue
        if resolve_player_team(p, player_teams) is not None:
            continue
        danger = calculate_player_danger(p, team=None)
        unassigned.append((p, danger))

    if not unassigned:
        return None

    unassigned.sort(key=_player_sort_key)
    for p, d in unassigned:
        if d.status in ("known", "nicked"):
            return d.username
    return unassigned[0][1].username
