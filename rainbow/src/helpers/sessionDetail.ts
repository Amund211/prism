import type { History } from "#queries/history.ts";
import type { StatsPIT } from "#queries/playerdata.ts";
import type {
    GameOutcome,
    GameResult,
    GameSegment,
    Gamemode,
} from "#queries/sessionAt.ts";
import type { Session } from "#queries/sessions.ts";
import { computeStat } from "#stats/index.ts";
import { REAL_GAMEMODE_KEYS } from "#stats/keys.ts";
import { computeStatProgression, nextCloseMilestone } from "#stats/progression.ts";
import { bedwarsLevelFromExp } from "#stats/stars.ts";
import { MS_PER_DAY, MS_PER_HOUR } from "#time.ts";

// The five core modes broken out on the session detail page, sourced from the
// canonical mode list so adding a mode doesn't require editing a second copy.
export const GAMEMODES: readonly Gamemode[] = REAL_GAMEMODE_KEYS;

export interface SessionAggregate {
    readonly games: number;
    readonly wins: number;
    readonly losses: number;
    readonly fk: number;
    readonly fd: number;
    readonly bb: number;
    readonly bl: number;
    readonly k: number;
    readonly d: number;
    readonly xp: number;
    readonly stars: number;
    readonly fkdr: number;
    readonly lifetimeFkdr: number;
    readonly winRate: number;
    readonly lifetimeWR: number;
    readonly elapsedMs: number;
}

const ratio = (numerator: number, denominator: number): number =>
    denominator === 0 ? numerator : numerator / denominator;

// The raw counter deltas between two point-in-time snapshots of one gamemode.
interface StatDelta {
    readonly games: number;
    readonly wins: number;
    readonly losses: number;
    readonly fk: number;
    readonly fd: number;
    readonly bb: number;
    readonly bl: number;
    readonly k: number;
    readonly d: number;
}

export const statDelta = (first: StatsPIT, last: StatsPIT): StatDelta => ({
    games: last.gamesPlayed - first.gamesPlayed,
    wins: last.wins - first.wins,
    losses: last.losses - first.losses,
    fk: last.finalKills - first.finalKills,
    fd: last.finalDeaths - first.finalDeaths,
    bb: last.bedsBroken - first.bedsBroken,
    bl: last.bedsLost - first.bedsLost,
    k: last.kills - first.kills,
    d: last.deaths - first.deaths,
});

export const aggregate = (session: Session): SessionAggregate => {
    const delta = statDelta(session.start.overall, session.end.overall);
    const xp = session.end.experience - session.start.experience;
    const stars =
        bedwarsLevelFromExp(session.end.experience) -
        bedwarsLevelFromExp(session.start.experience);
    // Route the ratio stats through computeStat so the session detail page and
    // the rest of the app share one ratio semantic. "session" measures the
    // delta across [start, end]; "overall" reads the lifetime value at a point.
    const history: History = [session.start, session.end];
    return {
        ...delta,
        xp,
        stars,
        fkdr: computeStat(session.end, "overall", "fkdr", "session", history),
        lifetimeFkdr: computeStat(session.start, "overall", "fkdr", "overall", history),
        winRate: computeStat(session.end, "overall", "winrate", "session", history),
        lifetimeWR: computeStat(
            session.start,
            "overall",
            "winrate",
            "overall",
            history,
        ),
        elapsedMs: session.end.queriedAt.getTime() - session.start.queriedAt.getTime(),
    };
};

export type SessionTagKey = "flawless" | "perfect" | "on_fire" | "marathon";

/**
 * Which auto-derived "badges" a session earns. `flawless` and `perfect` are
 * mutually exclusive — flawless is the stronger claim (no losses *and* no final
 * deaths), so it wins when both would apply.
 */
export const sessionTagKeys = (agg: SessionAggregate): SessionTagKey[] => {
    const keys: SessionTagKey[] = [];

    if (agg.games >= 2 && agg.losses === 0 && agg.fd === 0) {
        keys.push("flawless");
        // "Won every game" means exactly that: check wins against games rather
        // than losses === 0, which would count a draw as a win.
    } else if (agg.games >= 3 && agg.wins === agg.games) {
        keys.push("perfect");
    }

    if (agg.fkdr > agg.lifetimeFkdr * 1.4 && agg.fk >= 6) {
        keys.push("on_fire");
    }

    const hours = agg.elapsedMs / MS_PER_HOUR;
    if (hours >= 3) {
        keys.push("marathon");
    }

    return keys;
};

export type FkdrComparison = "beating" | "on_par" | "below";

/**
 * Classify the session FKDR against lifetime three ways: clearly above (≥ +10%)
 * is "beating", clearly below (≤ −10%) is "below", and within ±10% is "on_par".
 * A ±10% band keeps a session that merely matches lifetime from reading as a win
 * or a loss.
 */
export const fkdrVsLifetime = (agg: SessionAggregate): FkdrComparison => {
    let fkdrRatio: number;
    if (agg.lifetimeFkdr > 0) {
        fkdrRatio = agg.fkdr / agg.lifetimeFkdr;
    } else {
        fkdrRatio = agg.fkdr > 0 ? Infinity : 1;
    }
    if (fkdrRatio >= 1.1) return "beating";
    if (fkdrRatio <= 0.9) return "below";
    return "on_par";
};

export interface ModeStats {
    readonly games: number;
    readonly wins: number;
    readonly losses: number;
    readonly winRate: number;
    readonly fk: number;
    readonly fd: number;
    readonly fkdr: number;
    readonly bb: number;
    readonly bl: number;
    readonly k: number;
    readonly d: number;
    readonly kdr: number;
}

const ZERO_DELTA: StatDelta = {
    games: 0,
    wins: 0,
    losses: 0,
    fk: 0,
    fd: 0,
    bb: 0,
    bl: 0,
    k: 0,
    d: 0,
};

const addDelta = (a: StatDelta, b: StatDelta): StatDelta => ({
    games: a.games + b.games,
    wins: a.wins + b.wins,
    losses: a.losses + b.losses,
    fk: a.fk + b.fk,
    fd: a.fd + b.fd,
    bb: a.bb + b.bb,
    bl: a.bl + b.bl,
    k: a.k + b.k,
    d: a.d + b.d,
});

const subtractDelta = (a: StatDelta, b: StatDelta): StatDelta => ({
    games: a.games - b.games,
    wins: a.wins - b.wins,
    losses: a.losses - b.losses,
    fk: a.fk - b.fk,
    fd: a.fd - b.fd,
    bb: a.bb - b.bb,
    bl: a.bl - b.bl,
    k: a.k - b.k,
    d: a.d - b.d,
});

const toModeStats = (de: StatDelta): ModeStats => ({
    games: de.games,
    wins: de.wins,
    losses: de.losses,
    winRate: ratio(de.wins, de.games),
    fk: de.fk,
    fd: de.fd,
    fkdr: ratio(de.fk, de.fd),
    bb: de.bb,
    bl: de.bl,
    k: de.k,
    d: de.d,
    kdr: ratio(de.k, de.d),
});

// The five core modes plus an "other" bucket for everything else (Dreams
// modes) that the wire contract folds into `overall` but doesn't break out.
export type ModeBreakdownKey = Gamemode | "other";

export const modeBreakdown = (
    session: Session,
): Record<ModeBreakdownKey, ModeStats> => {
    const out = {} as Record<ModeBreakdownKey, ModeStats>;
    let core = ZERO_DELTA;
    for (const mode of GAMEMODES) {
        const delta = statDelta(session.start[mode], session.end[mode]);
        out[mode] = toModeStats(delta);
        core = addDelta(core, delta);
    }
    // Some players have strange stats where sum(gamemodes) != overall
    // surface that here in case it happens.
    const overall = statDelta(session.start.overall, session.end.overall);
    out.other = toModeStats(subtractDelta(overall, core));
    return out;
};

/**
 * Count how many games happened in a segment with no derivable per-game
 * stats. Returns 0 for a no-game window (no stats moved), N>=1 for a segment
 * that covers N games we couldn't split (e.g. gamesPlayed jumped by 2).
 *
 * Uses `overall.gamesPlayed`, not the five core modes — games played in a
 * non-core mode (a Dreams mode) move overall but leave solo/doubles/threes/
 * fours/4v4 flat, so summing the five would miss them entirely.
 */
export const inferredGameCount = (seg: GameSegment): number =>
    Math.max(0, seg.end.overall.gamesPlayed - seg.start.overall.gamesPlayed);

export interface SegmentGameNumber {
    /**
     * 1-based number of the first game in this segment by running game count,
     * or null for a no-game window (it advanced the count by zero, so it gets
     * no game number).
     */
    readonly first: number | null;
    /** Number of the last game — equal to `first` for a single game. */
    readonly last: number | null;
    /** Games this segment covers (0 for a no-game window). */
    readonly count: number;
}

/**
 * Number every segment by the running game count so the momentum strip,
 * highlights and trajectory chart all agree on which game is which. A real
 * single-game segment covers one game; a multi-game gap covers
 * `inferredGameCount` games; a no-game window covers zero and gets no number.
 */
export const segmentGameNumbers = (
    segments: readonly GameSegment[],
): SegmentGameNumber[] => {
    let gamesSoFar = 0;
    return segments.map((seg) => {
        const count = seg.game === null ? inferredGameCount(seg) : 1;
        if (count === 0) {
            return { first: null, last: null, count: 0 };
        }
        const first = gamesSoFar + 1;
        gamesSoFar += count;
        return { first, last: gamesSoFar, count };
    });
};

/**
 * Compact label for a segment's game number(s): `G3` for a single game,
 * `G5-7` for a multi-game gap, or null for a no-game window.
 */
export const gameNumberLabel = (num: SegmentGameNumber): string | null => {
    if (num.first === null || num.last === null) return null;
    return num.first === num.last
        ? `G${num.first.toString()}`
        : `G${num.first.toString()}-${num.last.toString()}`;
};

export interface TrajectoryPoint {
    /**
     * X-axis label for the point: `G3` for a single game, `G5-7` for a
     * multi-game gap spanning games 5 through 7.
     */
    readonly label: string;
    readonly sessionFkdr: number;
    readonly lifetimeFkdr: number;
}

/**
 * Compute the FKDR trajectory: the cumulative session FKDR and the live
 * lifetime FKDR after each game, numbered by the running game count rather
 * than by segment index.
 *
 *  - A real single-game segment is one point, labelled `G{n}`.
 *  - A multi-game gap (games we couldn't split apart) is one point spanning
 *    the games it covers, labelled `G{first}-{last}`.
 *  - A no-game window moves no finals, so it's dropped entirely rather than
 *    drawn as a flat, misleadingly game-numbered point.
 */
export const fkdrTrajectory = (
    session: Session,
    segments: readonly GameSegment[],
): TrajectoryPoint[] => {
    const numbers = segmentGameNumbers(segments);
    const points: TrajectoryPoint[] = [];
    for (const [i, seg] of segments.entries()) {
        const label = gameNumberLabel(numbers[i]);
        if (label === null) {
            // No-game window: FKDR is unchanged here, so it adds nothing.
            continue;
        }
        points.push({
            label,
            sessionFkdr: computeStat(seg.end, "overall", "fkdr", "session", [
                session.start,
                seg.end,
            ]),
            lifetimeFkdr: computeStat(seg.end, "overall", "fkdr", "overall", [
                session.start,
                seg.end,
            ]),
        });
    }
    return points;
};

export interface Milestone {
    readonly key: "prestige" | "wins" | "fkdr";
    readonly label: string;
    readonly current: number;
    /** The next milestone value, or null when no progress was made this session. */
    readonly target: number | null;
    readonly format: (v: number) => string;
    readonly deltaFormat: () => string;
    /** How many sessions like this one to reach the target (∞ if not on pace). */
    readonly sessions: number;
    /** Projected playtime to reach the target, in ms (0 if not on pace). */
    readonly playtimeMs: number;
    /** Set when the target is unreachable at this session's pace. */
    readonly blockedReason: string | null;
}

interface MilestoneSpec {
    readonly key: Milestone["key"];
    readonly label: string;
    readonly stat: "stars" | "wins" | "fkdr";
    readonly format: (v: number) => string;
    readonly deltaFormat: () => string;
    readonly currentFallback: number;
}

/**
 * Milestones for the session, computed with the *same* projection helper the
 * regular session page uses (`computeStatProgression`), so the milestone
 * targets and ETAs always agree between the two pages.
 *
 * The trick: feed the session itself as the tracking interval. The pace is then
 * "progress per session-worth of play", so `daysUntilMilestone` comes back as
 * the projected playtime to reach the target — which divided by the session
 * length is "X sessions like this".
 */
export const computeMilestones = (
    session: Session,
    agg: SessionAggregate,
): Milestone[] => {
    const history: History = [session.start, session.end];
    const trackingEnd = session.end.queriedAt;
    const sessionMs = agg.elapsedMs;
    const last = session.end;

    const specs: readonly MilestoneSpec[] = [
        {
            key: "prestige",
            label: "Next stars milestone",
            stat: "stars",
            format: (v) => `✦${v.toFixed(0)}`,
            deltaFormat: () => `+${agg.stars.toFixed(2)}/session`,
            currentFallback: bedwarsLevelFromExp(last.experience),
        },
        {
            key: "wins",
            label: "Next wins milestone",
            stat: "wins",
            format: (v) => v.toLocaleString(),
            deltaFormat: () => `+${agg.wins.toString()}/session`,
            currentFallback: last.overall.wins,
        },
        {
            key: "fkdr",
            label: "Next FKDR milestone",
            stat: "fkdr",
            format: (v) => v.toFixed(2),
            deltaFormat: () => `session: ${agg.fkdr.toFixed(2)}`,
            currentFallback: ratio(last.overall.finalKills, last.overall.finalDeaths),
        },
    ];

    return specs.map((spec): Milestone => {
        const progression = computeStatProgression(
            history,
            trackingEnd,
            spec.stat,
            "overall",
            // Closer, more reachable targets than the default — the session
            // detail page wants goals that are only a session or two out.
            nextCloseMilestone,
        );
        if (progression.error) {
            return {
                key: spec.key,
                label: spec.label,
                current: spec.currentFallback,
                target: null,
                format: spec.format,
                deltaFormat: spec.deltaFormat,
                sessions: Number.POSITIVE_INFINITY,
                playtimeMs: 0,
                blockedReason: "No progress this session",
            };
        }

        const reachable = Number.isFinite(progression.daysUntilMilestone);
        const playtimeMs = reachable ? progression.daysUntilMilestone * MS_PER_DAY : 0;
        const sessions =
            reachable && sessionMs > 0
                ? playtimeMs / sessionMs
                : Number.POSITIVE_INFINITY;
        return {
            key: spec.key,
            label: spec.label,
            current: progression.endValue,
            target: progression.nextMilestoneValue,
            format: spec.format,
            deltaFormat: spec.deltaFormat,
            sessions,
            playtimeMs,
            blockedReason: reachable ? null : "Not on pace to reach this",
        };
    });
};

export const segmentDurationMs = (seg: GameSegment): number =>
    seg.end.queriedAt.getTime() - seg.start.queriedAt.getTime();

export const segmentExperience = (seg: GameSegment): number =>
    seg.end.experience - seg.start.experience;

/**
 * Best game = the single-game segment with the most final kills, breaking ties
 * first toward no final death, then toward no bed lost. Ambiguous segments
 * (no-game windows / multi-game gaps) are excluded.
 */
export const bestGame = (
    segments: readonly GameSegment[],
): (GameSegment & { game: GameResult }) | undefined => {
    const games = segments.filter(
        (seg): seg is GameSegment & { game: GameResult } => seg.game !== null,
    );
    const [best] = games.toSorted(
        (a, b) =>
            b.game.finalKills - a.game.finalKills ||
            Number(a.game.finalDeath) - Number(b.game.finalDeath) ||
            Number(a.game.bedLost) - Number(b.game.bedLost),
    );
    return best;
};

export const fastestWin = (
    segments: readonly GameSegment[],
): (GameSegment & { game: GameResult }) | undefined => {
    const wins = segments.filter(
        (seg): seg is GameSegment & { game: GameResult } =>
            seg.game !== null && seg.game.outcome === "win",
    );
    let fastest: (GameSegment & { game: GameResult }) | undefined;
    let fastestMs = Number.POSITIVE_INFINITY;
    for (const seg of wins) {
        const ms = segmentDurationMs(seg);
        if (ms < fastestMs) {
            fastest = seg;
            fastestMs = ms;
        }
    }
    return fastest;
};

/**
 * Trailing streak of identical outcomes across single-game segments
 * (ambiguous segments break the streak — we don't know individual
 * outcomes). Returns null when no meaningful streak exists.
 */
export const trailingStreak = (
    segments: readonly GameSegment[],
): { length: number; outcome: GameOutcome } | null => {
    let length = 0;
    let outcome: GameOutcome | undefined;
    for (let i = segments.length - 1; i >= 0; i--) {
        const { game } = segments[i];
        if (game === null) break;
        if (outcome === undefined) {
            ({ outcome } = game);
            length = 1;
            continue;
        }
        if (game.outcome === outcome) {
            length++;
        } else {
            break;
        }
    }
    if (length < 2 || outcome === undefined) return null;
    return { length, outcome };
};

// Per-mode thresholds for a "perfect game": the maximum final kills and beds
// broken available in a game of that mode. Hitting both means the player
// single-handedly cleared the lobby.
export const PERFECT_GAME_THRESHOLDS: Record<
    Gamemode,
    { finalKills: number; bedsBroken: number }
> = {
    solo: { finalKills: 7, bedsBroken: 7 },
    doubles: { finalKills: 14, bedsBroken: 7 },
    threes: { finalKills: 12, bedsBroken: 3 },
    fours: { finalKills: 16, bedsBroken: 3 },
    "4v4": { finalKills: 4, bedsBroken: 1 },
};

export const isPerfectGame = (game: GameResult): boolean => {
    const thresholds = PERFECT_GAME_THRESHOLDS[game.gamemode];
    return (
        game.finalKills >= thresholds.finalKills &&
        game.bedsBroken >= thresholds.bedsBroken
    );
};

export type GameAccoladeKind = "perfect" | "carried" | "clutch";

/**
 * The notable thing about a won game, if any. Precedence is mutually exclusive:
 * perfect > carried > clutch. Returns null for a loss/draw or an unremarkable
 * win. The caller maps the kind to an icon/colour/label.
 */
export const gameAccolade = (game: GameResult): GameAccoladeKind | null => {
    if (game.outcome !== "win") return null;
    if (isPerfectGame(game)) return "perfect";
    if (game.finalDeath) return "carried";
    if (game.bedLost) return "clutch";
    return null;
};
