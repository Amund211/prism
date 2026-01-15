import type { TimeInterval } from "#intervals.ts";
import type { History } from "#queries/history.ts";

import { getStat } from "./index.ts";
import type { GamemodeKey, StatKey } from "./keys.ts";
import { PRESTIGE_EXP } from "./stars.ts";

// Threshold below which a leading polynomial coefficient is treated as
// zero, dropping us to a lower-degree solver path.
const CUBIC_LEADING_COEFF_EPS = 1e-9;

// Roots smaller than this are treated as non-positive (i.e. "right now"
// or numerical noise around zero), and excluded from the result.
const CUBIC_POSITIVE_ROOT_EPS = 1e-9;

/*
 * Smallest t > 0 satisfying a*t^3 + b*t^2 + c*t + e = 0, or null if none.
 *
 * Strips leading zeros to drop to the actual polynomial degree (linear or
 * quadratic), and otherwise depresses the cubic via t = u - p/3 to
 * u^3 + P*u + Q = 0 and uses the trig formula (when P < 0 and |arg| <= 1)
 * or Cardano's formula. Branching on the natural |arg| <= 1 condition
 * avoids the brittle "discriminant ≈ 0" check.
 */
export const findSmallestPositiveCubicRoot = (
    a: number,
    b: number,
    c: number,
    e: number,
): number | null => {
    let roots: number[];

    if (Math.abs(a) < CUBIC_LEADING_COEFF_EPS) {
        if (Math.abs(b) < CUBIC_LEADING_COEFF_EPS) {
            if (Math.abs(c) < CUBIC_LEADING_COEFF_EPS) {
                return null;
            }
            const t = -e / c;
            return t > CUBIC_POSITIVE_ROOT_EPS ? t : null;
        }
        const disc = c * c - 4 * b * e;
        if (disc < 0) {
            return null;
        }
        const sd = Math.sqrt(disc);
        roots = [(-c - sd) / (2 * b), (-c + sd) / (2 * b)];
    } else {
        const p = b / a;
        const q = c / a;
        const r = e / a;
        const P = q - (p * p) / 3;
        const Q = (2 * p ** 3) / 27 - (p * q) / 3 + r;
        const shift = -p / 3;

        let uRoots: number[];
        if (P < 0) {
            const m = 2 * Math.sqrt(-P / 3);
            const arg = (3 * Q) / (P * m);
            if (Math.abs(arg) <= 1) {
                const theta = Math.acos(arg) / 3;
                uRoots = [
                    m * Math.cos(theta),
                    m * Math.cos(theta - (2 * Math.PI) / 3),
                    m * Math.cos(theta - (4 * Math.PI) / 3),
                ];
            } else {
                // |arg| > 1 implies delta > 0 mathematically, but the two
                // expressions go through different operation sequences so
                // computed delta can come out very slightly negative near
                // the boundary; clamp to keep sqrt real.
                const delta = (Q * Q) / 4 + P ** 3 / 27;
                const sd = Math.sqrt(Math.max(delta, 0));
                uRoots = [Math.cbrt(-Q / 2 + sd) + Math.cbrt(-Q / 2 - sd)];
            }
        } else {
            const delta = (Q * Q) / 4 + P ** 3 / 27;
            const sd = Math.sqrt(Math.max(delta, 0));
            uRoots = [Math.cbrt(-Q / 2 + sd) + Math.cbrt(-Q / 2 - sd)];
        }

        roots = uRoots.map((u) => u + shift);
    }

    let smallest: number | null = null;
    for (const t of roots) {
        if (t > CUBIC_POSITIVE_ROOT_EPS && (smallest === null || t < smallest)) {
            smallest = t;
        }
    }
    return smallest;
};

/*
 * Next round-number index milestone above (or below) `value`, scaled to the
 * value's order of magnitude. Going down at exactly a power of 10 drops one
 * order of magnitude (e.g. 100 -> 90, not 100 -> 0).
 */
const nextIndexMilestone = (value: number, trendingUpward: boolean): number => {
    if (value <= 0) {
        return 1;
    }
    if (trendingUpward) {
        const magnitude = 10 ** Math.floor(Math.log10(value));
        return (Math.floor(value / magnitude) + 1) * magnitude;
    }
    const adjusted = value * (1 - 1e-9);
    const magnitude = 10 ** Math.floor(Math.log10(adjusted));
    return Math.floor(adjusted / magnitude) * magnitude;
};

interface BaseStatProgression {
    trackingDataTimeInterval: TimeInterval;
    stat: StatKey;
    endValue: number;
    nextMilestoneValue: number;
    daysUntilMilestone: number;
    progressPerDay: number;
    trendingUpward: boolean;
    error?: undefined;
}

type QuotientProgression = BaseStatProgression & {
    stat: "fkdr" | "kdr";
    sessionQuotient: number;
    dividendPerDay: number;
    divisorPerDay: number;
};

type IndexProgression = BaseStatProgression & {
    stat: "index";
    starsPerDay: number;
    finalKillsPerDay: number;
    finalDeathsPerDay: number;
    sessionFkdr: number;
};

export type StatProgression =
    | (BaseStatProgression & { stat: Exclude<StatKey, "fkdr" | "kdr" | "index"> })
    | QuotientProgression
    | IndexProgression;

const computeQuotientProgression = (
    trackingHistory: History,
    trackingEnd: Date,
    stat: QuotientProgression["stat"],
    dividendStat: Exclude<StatKey, "winstreak">,
    divisorStat: Exclude<StatKey, "winstreak">,
    gamemode: GamemodeKey,
): QuotientProgression | { error: true; reason: string } => {
    const [start, end] = trackingHistory;
    const startDate = start.queriedAt;
    const endDate = trackingEnd;
    const daysElapsed =
        (endDate.getTime() - startDate.getTime()) / (24 * 60 * 60 * 1000);

    const startDividend = getStat(start, gamemode, dividendStat);
    const startDivisor = getStat(start, gamemode, divisorStat);
    const endDividend = getStat(end, gamemode, dividendStat);
    const endDivisor = getStat(end, gamemode, divisorStat);

    const sessionDividend = endDividend - startDividend;
    const sessionDivisor = endDivisor - startDivisor;

    const sessionQuotient =
        sessionDivisor === 0 ? sessionDividend : sessionDividend / sessionDivisor;

    const endQuotient = endDivisor === 0 ? endDividend : endDividend / endDivisor;

    const dividendPerDay = sessionDividend / daysElapsed;
    const divisorPerDay = sessionDivisor / daysElapsed;

    if (endDivisor === 0 && sessionDivisor === 0) {
        // Have "infinite" ratio at the end -> ratio is computed as just dividend
        // oxlint-disable-next-line eslint/no-use-before-define
        const dividendProgression = computeStatProgression(
            trackingHistory,
            trackingEnd,
            dividendStat,
            gamemode,
        );
        if (dividendProgression.error) {
            return dividendProgression;
        }
        return {
            ...dividendProgression,
            stat,
            dividendPerDay,
            divisorPerDay, // 0
            sessionQuotient,
            trendingUpward: true,
        };
    }

    const infiniteSessionQuotient = sessionDivisor === 0 && sessionDividend > 0;
    const noSessionProgress = sessionDividend === 0 && sessionDivisor === 0;
    // Trend upwards if the session quotient is greater than the end quotient
    // OR: if no progress was made during the tracking session -> just need somewhere to trend
    // OR: if the session quotient is infinite
    const trendingUpward =
        sessionQuotient >= endQuotient || noSessionProgress || infiniteSessionQuotient;

    // TODO: Smaller steps for smaller quotients
    const nextMilestoneValue = trendingUpward
        ? Math.floor(endQuotient) + 1
        : Math.ceil(endQuotient) - 1;

    if (
        // Will make no progress since the quotients are equal (as long as the session quotient is not infinite)
        (sessionQuotient === endQuotient && !infiniteSessionQuotient) ||
        // No progress is being made on the divisor or the dividend -> No progress on the quotient
        noSessionProgress
    ) {
        // Will make no progress -> Display milestone and infinite time
        return {
            stat,
            trackingDataTimeInterval: { start: startDate, end: endDate },
            endValue: endQuotient,
            nextMilestoneValue,
            daysUntilMilestone: Infinity,
            // NOTE: Progres per day changes over time
            progressPerDay: 0,
            sessionQuotient,
            dividendPerDay,
            divisorPerDay,
            trendingUpward,
        };
    }

    // Variables:
    // k0 = endDividend
    // k  = dividendPerDay
    // d0 = endDivisor
    // d  = divisorPerDay
    // t  = daysToNextMilestone
    // M  = nextMilestoneValue
    //
    // Solve for t:
    // (k0 + kt) / (d0 + dt) = M
    // k0 + kt = Md0 + Mdt         ((d0 + dt > 0) d0 + d > 0 validated above, t chosen to be non-negative by choosing M appropriately)
    // (k - Md) t = Md0 - k0
    // t = (Md0 - k0) / (k - Md)

    if (
        trendingUpward
            ? nextMilestoneValue >= sessionQuotient && !infiniteSessionQuotient
            : nextMilestoneValue <= sessionQuotient
    ) {
        // If the milestone is out of reach given the session quotient:
        // Won't make it all the way to the milestone, only approach the session quotient
        // -> Display "reachable" milestone (session quotient) and infinite time
        //
        // If the next milestone is equal to the session quotient:
        // (k - Md) = 0
        // k = Md
        // M = k / d (= sessionQuotient)
        // Will approach but never reach milestone
        // -> Display milestone and infinite time
        return {
            stat,
            trackingDataTimeInterval: { start: startDate, end: endDate },
            endValue: endQuotient,
            nextMilestoneValue,
            daysUntilMilestone: Infinity,
            // NOTE: Progres per day changes over time
            progressPerDay: 0,
            sessionQuotient,
            dividendPerDay,
            divisorPerDay,
            trendingUpward,
        };
    }

    // t = (Md0 - k0) / (k - Md)
    // NOTE: May be infinite
    const daysUntilMilestone =
        (nextMilestoneValue * endDivisor - endDividend) /
        (dividendPerDay - nextMilestoneValue * divisorPerDay);

    return {
        stat,
        trackingDataTimeInterval: { start: startDate, end: endDate },
        endValue: endQuotient,
        nextMilestoneValue,
        daysUntilMilestone,
        // NOTE: Progres per day changes over time
        progressPerDay: (nextMilestoneValue - endQuotient) / daysUntilMilestone,
        sessionQuotient,
        dividendPerDay,
        divisorPerDay,
        trendingUpward,
    };
};

export const ERR_NO_DATA = "No data";
export const ERR_TRACKING_STARTED = "Tracking started!";

export const computeStatProgression = (
    trackingHistory: History | undefined,
    trackingEnd: Date,
    stat: StatKey,
    gamemode: GamemodeKey,
): StatProgression | { error: true; reason: string } => {
    if (trackingHistory === undefined || trackingHistory.length === 0) {
        return { error: true, reason: ERR_NO_DATA };
    }

    if (trackingHistory.length === 1) {
        return { error: true, reason: ERR_TRACKING_STARTED };
    }

    if (trackingHistory.length > 2) {
        return { error: true, reason: "Expected at most 2 data points" };
    }

    const [start, end] = trackingHistory;
    const startDate = start.queriedAt;
    const endDate = trackingEnd;
    const daysElapsed =
        (endDate.getTime() - startDate.getTime()) / (24 * 60 * 60 * 1000);

    switch (stat) {
        case "stars": {
            const startExp = getStat(start, gamemode, "experience");
            const endExp = getStat(end, gamemode, "experience");
            const endStars = getStat(end, gamemode, "stars");

            const expPerDay = (endExp - startExp) / daysElapsed;

            // NOTE: Slightly inaccurate over short distances as it does not account for the different exp requirements for different levels
            const starsPerDay = expPerDay / (PRESTIGE_EXP / 100);

            const nextPrestige = Math.floor(endStars / 100) + 1;
            const nextPrestigeExp = nextPrestige * PRESTIGE_EXP;
            const expToNextPrestige = nextPrestigeExp - endExp;
            const daysToNextPrestige = expToNextPrestige / expPerDay;
            return {
                stat,
                trackingDataTimeInterval: { start: startDate, end: endDate },
                endValue: endStars,
                nextMilestoneValue: nextPrestige * 100,
                daysUntilMilestone: daysToNextPrestige,
                progressPerDay: starsPerDay,
                trendingUpward: true,
            };
        }
        case "fkdr": {
            return computeQuotientProgression(
                trackingHistory,
                trackingEnd,
                stat,
                "finalKills",
                "finalDeaths",
                gamemode,
            );
        }
        case "kdr": {
            return computeQuotientProgression(
                trackingHistory,
                trackingEnd,
                stat,
                "kills",
                "deaths",
                gamemode,
            );
        }
        case "index": {
            // index(t) = (s_0 + s*t) * (k_0 + k*t)^2 / (d_0 + d*t)^2,
            // or (s_0 + s*t) * (k_0 + k*t)^2 when fkdr is computed as
            // just finalKills (d_0 = d = 0). Setting index(t) = M and
            // clearing the denominator gives a cubic in t whose smallest
            // positive real root is daysUntilMilestone.
            const startExp = getStat(start, gamemode, "experience");
            const endExp = getStat(end, gamemode, "experience");
            const endStars = getStat(end, gamemode, "stars");
            const startFK = getStat(start, gamemode, "finalKills");
            const endFK = getStat(end, gamemode, "finalKills");
            const startFD = getStat(start, gamemode, "finalDeaths");
            const endFD = getStat(end, gamemode, "finalDeaths");

            const s0 = endStars;
            const s = (endExp - startExp) / (PRESTIGE_EXP / 100) / daysElapsed;
            const k0 = endFK;
            const k = (endFK - startFK) / daysElapsed;
            const d0 = endFD;
            const d = (endFD - startFD) / daysElapsed;
            const endIndex = getStat(end, gamemode, "index");

            const isFkdrAsKills = d0 === 0 && d === 0;

            // Sign of d/dt index(0) (after multiplying by d_0^3 > 0 in the
            // general case). Ties default to upward.
            const trendNumerator = isFkdrAsKills
                ? s * k0 * k0 + 2 * s0 * k0 * k
                : s * k0 * k0 * d0 + 2 * s0 * k0 * k * d0 - 2 * s0 * k0 * k0 * d;
            const trendingUpward = trendNumerator >= 0;

            const M = nextIndexMilestone(endIndex, trendingUpward);

            const a = s * k * k;
            const b = isFkdrAsKills
                ? s0 * k * k + 2 * s * k0 * k
                : s0 * k * k + 2 * s * k0 * k - M * d * d;
            const c = isFkdrAsKills
                ? 2 * s0 * k0 * k + s * k0 * k0
                : 2 * s0 * k0 * k + s * k0 * k0 - 2 * M * d0 * d;
            const e = isFkdrAsKills ? s0 * k0 * k0 - M : s0 * k0 * k0 - M * d0 * d0;

            const daysUntilMilestone =
                findSmallestPositiveCubicRoot(a, b, c, e) ?? Infinity;
            // Match the quotient progression's convention: explicit 0
            // when unreachable, so we don't surface -0 from `(neg)/Infinity`.
            const progressPerDay = Number.isFinite(daysUntilMilestone)
                ? (M - endIndex) / daysUntilMilestone
                : 0;

            return {
                stat,
                trackingDataTimeInterval: { start: startDate, end: endDate },
                endValue: endIndex,
                nextMilestoneValue: M,
                daysUntilMilestone,
                progressPerDay,
                trendingUpward,
                starsPerDay: s,
                finalKillsPerDay: k,
                finalDeathsPerDay: d,
                sessionFkdr: d === 0 ? k : k / d,
            };
        }
        case "experience":
        case "gamesPlayed":
        case "wins":
        case "losses":
        case "bedsBroken":
        case "bedsLost":
        case "finalKills":
        case "finalDeaths":
        case "kills":
        case "deaths": {
            const startValue = getStat(start, gamemode, stat);
            const endValue = getStat(end, gamemode, stat);
            const increasePerDay = (endValue - startValue) / daysElapsed;

            if (increasePerDay === 0) {
                // Will make no progress
                // TODO: Display upward milestone and infinite time
                return {
                    error: true,
                    reason: "No progress",
                };
            }

            const endMagnitude = 10 ** Math.floor(Math.log10(endValue));
            // TODO: More meaningful milestones (e.g. 100, 250, 500, 1000, 2500, 5000, 10000, 20000, 30000, ...)
            // TODO: Pick your own milestone
            const nextMilestoneValue =
                (Math.floor(endValue / endMagnitude) + 1) * endMagnitude;

            const daysUntilMilestone = (nextMilestoneValue - endValue) / increasePerDay;

            return {
                stat,
                trackingDataTimeInterval: { start: startDate, end: endDate },
                endValue,
                nextMilestoneValue,
                daysUntilMilestone,
                progressPerDay: increasePerDay,
                trendingUpward: true,
            };
        }

        case "winstreak": {
            return { error: true, reason: "Not implemented" };
        }
        default: {
            stat satisfies never;
        }
    }

    return { error: true, reason: "Unknown stat" };
};
