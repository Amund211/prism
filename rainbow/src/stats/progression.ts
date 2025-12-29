import { type TimeInterval } from "#intervals.ts";
import { type History } from "#queries/history.ts";
import { getStat } from "./index.ts";
import { type GamemodeKey, type StatKey } from "./keys.ts";
import { PRESTIGE_EXP } from "./stars.ts";

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

export type StatProgression =
    | (BaseStatProgression & { stat: Exclude<StatKey, "fkdr" | "kdr"> })
    | QuotientProgression;

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
        sessionDivisor === 0
            ? sessionDividend
            : sessionDividend / sessionDivisor;

    const endQuotient =
        endDivisor === 0 ? endDividend : endDividend / endDivisor;

    const dividendPerDay = sessionDividend / daysElapsed;
    const divisorPerDay = sessionDivisor / daysElapsed;

    if (endDivisor === 0 && sessionDivisor === 0) {
        // Have "infinite" ratio at the end -> ratio is computed as just dividend
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

    const noSessionProgress = sessionDividend === 0 && sessionDivisor === 0;
    // Trend upwards if the session quotient is greater than the end quotient
    // OR: if no progress was made during the tracking session -> just need somewhere to trend
    const trendingUpward = sessionQuotient >= endQuotient || noSessionProgress;

    // TODO: Smaller steps for smaller quotients
    const nextMilestoneValue = trendingUpward
        ? Math.floor(endQuotient) + 1
        : Math.ceil(endQuotient) - 1;

    if (
        // Will make no progress since the quotients are equal
        sessionQuotient === endQuotient ||
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
            ? nextMilestoneValue >= sessionQuotient
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
        case "fkdr":
            return computeQuotientProgression(
                trackingHistory,
                trackingEnd,
                stat,
                "finalKills",
                "finalDeaths",
                gamemode,
            );
        case "kdr":
            return computeQuotientProgression(
                trackingHistory,
                trackingEnd,
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
            const increasePerDay = (endValue - startValue) / daysElapsed;

            if (increasePerDay === 0) {
                // Will make no progress
                // TODO: Display upward milestone and infinite time
                return {
                    error: true,
                    reason: "No progress",
                };
            }

            const endMagnitude = Math.pow(10, Math.floor(Math.log10(endValue)));
            // TODO: More meaningful milestones (e.g. 100, 250, 500, 1000, 2500, 5000, 10000, 20000, 30000, ...)
            // TODO: Pick your own milestone
            const nextMilestoneValue =
                (Math.floor(endValue / endMagnitude) + 1) * endMagnitude;

            const daysUntilMilestone =
                (nextMilestoneValue - endValue) / increasePerDay;

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

        case "winstreak":
            return { error: true, reason: "Not implemented" };
        default:
            stat satisfies never;
    }

    return { error: true, reason: "Unknown stat" };
};
