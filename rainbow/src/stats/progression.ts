import { type TimeInterval } from "#intervals.ts";
import { type History } from "#queries/history.ts";
import { type PlayerDataPIT } from "#queries/playerdata.ts";
import { getStat } from ".";
import { type GamemodeKey, type StatKey } from "./keys";
import { PRESTIGE_EXP } from "./stars";

interface BaseStatProgression {
    trackingDataTimeInterval: TimeInterval;
    stat: StatKey;
    currentValue: number;
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

export type StatProgression =
    | (BaseStatProgression & { stat: Exclude<StatKey, "fkdr" | "kdr"> })
    | QuotientProgression;

const computeQuotientProgression = (
    trackingHistory: History,
    currentStats: PlayerDataPIT,
    stat: QuotientProgression["stat"],
    dividendStat: Exclude<StatKey, "winstreak">,
    divisorStat: Exclude<StatKey, "winstreak">,
    gamemode: GamemodeKey,
): QuotientProgression | { error: true; reason: string } => {
    const [start, end] = trackingHistory;
    const startDate = start.queriedAt;
    const endDate = end.queriedAt;
    const daysElapsed =
        (endDate.getTime() - startDate.getTime()) / (24 * 60 * 60 * 1000);

    const startDividend = getStat(start, gamemode, dividendStat);
    const startDivisor = getStat(start, gamemode, divisorStat);
    const endDividend = getStat(end, gamemode, dividendStat);
    const endDivisor = getStat(end, gamemode, divisorStat);
    const currentDividend = getStat(currentStats, gamemode, dividendStat);
    const currentDivisor = getStat(currentStats, gamemode, divisorStat);

    const sessionDividend = endDividend - startDividend;
    const sessionDivisor = endDivisor - startDivisor;

    const sessionQuotient =
        sessionDivisor === 0
            ? sessionDividend
            : sessionDividend / sessionDivisor;

    const currentQuotient =
        currentDivisor === 0
            ? currentDividend
            : currentDividend / currentDivisor;

    const dividendPerDay = sessionDividend / daysElapsed;
    const divisorPerDay = sessionDivisor / daysElapsed;

    if (currentDivisor === 0 && sessionDivisor === 0) {
        // Currently have "infinite" ratio -> ratio is computed as just dividend
        const dividendProgression = computeStatProgression(
            trackingHistory,
            currentStats,
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

    const noSessionProgress = sessionDividend === 0 && sessionDivisor === 0;
    // Trend upwards if the session quotient is greater than the current quotient
    // OR: if no progress was made during the tracking session -> just need somewhere to trend
    const trendingUpward =
        sessionQuotient >= currentQuotient || noSessionProgress;

    // TODO: Smaller steps for smaller quotients
    const nextMilestoneValue = trendingUpward
        ? Math.floor(currentQuotient) + 1
        : Math.ceil(currentQuotient) - 1;

    if (
        // Will make no progress since the quotients are equal
        sessionQuotient === currentQuotient ||
        // No progress is being made on the divisor or the dividend -> No progress on the quotient
        noSessionProgress
    ) {
        // Will make no progress -> Display milestone and infinite time
        return {
            stat,
            trackingDataTimeInterval: { start: startDate, end: endDate },
            currentValue: currentQuotient,
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
    // k0 = currentDividend
    // k  = dividendPerDay
    // d0 = currentDivisor
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
            ? nextMilestoneValue >= sessionQuotient
            : nextMilestoneValue <= sessionQuotient
    ) {
        // If the milestone is out of reach given the current session quotient:
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
            currentValue: currentQuotient,
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
        (nextMilestoneValue * currentDivisor - currentDividend) /
        (dividendPerDay - nextMilestoneValue * divisorPerDay);

    return {
        stat,
        trackingDataTimeInterval: { start: startDate, end: endDate },
        currentValue: currentQuotient,
        nextMilestoneValue,
        daysUntilMilestone,
        // NOTE: Progres per day changes over time
        progressPerDay:
            (nextMilestoneValue - currentQuotient) / daysUntilMilestone,
        sessionQuotient,
        dividendPerDay,
        divisorPerDay,
        trendingUpward,
    };
};
export const computeStatProgression = (
    trackingHistory: History | undefined,
    currentStats: PlayerDataPIT | undefined,
    stat: StatKey,
    gamemode: GamemodeKey,
): StatProgression | { error: true; reason: string } => {
    if (trackingHistory === undefined || trackingHistory.length === 0) {
        return { error: true, reason: "No data" };
    }

    if (trackingHistory.length === 1) {
        return { error: true, reason: "Not enough data" };
    }

    if (trackingHistory.length > 2) {
        return { error: true, reason: "Expected at most 2 data points" };
    }

    if (currentStats === undefined) {
        return { error: true, reason: "No current stats" };
    }

    const [start, end] = trackingHistory;
    const startDate = start.queriedAt;
    const endDate = end.queriedAt;
    const daysElapsed =
        (endDate.getTime() - startDate.getTime()) / (24 * 60 * 60 * 1000);

    switch (stat) {
        case "stars": {
            const startExp = getStat(start, gamemode, "experience");
            const endExp = getStat(end, gamemode, "experience");
            const currentExp = getStat(currentStats, gamemode, "experience");
            const currentStars = getStat(currentStats, gamemode, "stars");

            const expPerDay = (endExp - startExp) / daysElapsed;

            // NOTE: Slightly inaccurate over short distances as it does not account for the different exp requirements for different levels
            const starsPerDay = expPerDay / (PRESTIGE_EXP / 100);

            const nextPrestige = Math.floor(currentStars / 100) + 1;
            const nextPrestigeExp = nextPrestige * PRESTIGE_EXP;
            const expToNextPrestige = nextPrestigeExp - currentExp;
            const daysToNextPrestige = expToNextPrestige / expPerDay;
            return {
                stat,
                trackingDataTimeInterval: { start: startDate, end: endDate },
                currentValue: currentStars,
                nextMilestoneValue: nextPrestige * 100,
                daysUntilMilestone: daysToNextPrestige,
                progressPerDay: starsPerDay,
                trendingUpward: true,
            };
        }
        case "fkdr":
            return computeQuotientProgression(
                trackingHistory,
                currentStats,
                stat,
                "finalKills",
                "finalDeaths",
                gamemode,
            );
        case "kdr":
            return computeQuotientProgression(
                trackingHistory,
                currentStats,
                stat,
                "kills",
                "deaths",
                gamemode,
            );
        case "index":
            // TODO
            // Potential strategy:
            // Compute progression on experience, finals, final deaths
            // If there is any star progression, any upward milestone can be reached
            // Make a function index(t), and search for the intersection of index(t) and goal
            // Potentially erroring if something goes wrong
            // NOTE: index(t) is not necessarily monotonic, so there can be multiple intersections
            return { error: true, reason: "Not implemented" };
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
            const currentValue = getStat(currentStats, gamemode, stat);
            const increasePerDay = (endValue - startValue) / daysElapsed;

            if (increasePerDay === 0) {
                // Will make no progress
                // TODO: Display upward milestone and infinite time
                return {
                    error: true,
                    reason: "No progress",
                };
            }

            const currentMagniture = Math.pow(
                10,
                Math.floor(Math.log10(currentValue)),
            );
            // TODO: More meaningful milestones (e.g. 100, 250, 500, 1000, 2500, 5000, 10000, 20000, 30000, ...)
            // TODO: Pick your own milestone
            const nextMilestoneValue =
                (Math.floor(currentValue / currentMagniture) + 1) *
                currentMagniture;

            const daysUntilMilestone =
                (nextMilestoneValue - currentValue) / increasePerDay;

            return {
                stat,
                trackingDataTimeInterval: { start: startDate, end: endDate },
                currentValue,
                nextMilestoneValue,
                daysUntilMilestone,
                progressPerDay: increasePerDay,
                trendingUpward: true,
            };
        }

        case "winstreak":
            return { error: true, reason: "Not implemented" };
        default:
            stat satisfies never;
    }

    return { error: true, reason: "Unknown stat" };
};
