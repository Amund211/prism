import { TimeInterval } from "#intervals.ts";
import { History, PlayerDataPIT } from "#queries/history.ts";
import { getStat } from ".";
import { GamemodeKey, StatKey } from "./keys";
import { PRESTIGE_EXP } from "./stars";

interface BaseStatProgression {
    trackingDataTimeInterval: TimeInterval;
    stat: StatKey;
    currentValue: number;
    nextMilestoneValue: number;
    projectedMilestoneDate: Date;
    referenceDate: Date;
    progressPerDay: number;
    error?: undefined;
}

type FKDRProgression = BaseStatProgression & {
    stat: "fkdr";
    sessionFKDR: number;
    finalKillsPerDay: number;
    finalDeathsPerDay: number;
};

export type StatProgression =
    | (BaseStatProgression & { stat: Exclude<StatKey, "fkdr"> })
    | FKDRProgression;

export const computeStatProgression = (
    trackingHistory: History | undefined,
    currentStats: PlayerDataPIT | undefined,
    referenceDate: Date,
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
            const projectedMilestoneDate = new Date(
                referenceDate.getTime() +
                    daysToNextPrestige * 24 * 60 * 60 * 1000,
            );
            return {
                stat,
                trackingDataTimeInterval: { start: startDate, end: endDate },
                currentValue: currentStars,
                nextMilestoneValue: nextPrestige * 100,
                projectedMilestoneDate,
                referenceDate,
                progressPerDay: starsPerDay,
            };
        }
        case "fkdr": {
            const startFinalKills = getStat(start, gamemode, "finalKills");
            const startFinalDeaths = getStat(start, gamemode, "finalDeaths");
            const endFinalKills = getStat(end, gamemode, "finalKills");
            const endFinalDeaths = getStat(end, gamemode, "finalDeaths");

            const sessionFinalKills = endFinalKills - startFinalKills;
            const sessionFinalDeaths = endFinalDeaths - startFinalDeaths;

            const currentFinalKills = getStat(
                currentStats,
                gamemode,
                "finalKills",
            );
            const currentFinalDeaths = getStat(
                currentStats,
                gamemode,
                "finalDeaths",
            );

            // FIXME: Factor out fkdr computation
            const sessionFKDR =
                sessionFinalDeaths === 0
                    ? sessionFinalKills
                    : sessionFinalKills / sessionFinalDeaths;

            const currentFKDR =
                currentFinalDeaths === 0
                    ? currentFinalKills
                    : currentFinalKills / currentFinalDeaths;

            const finalKillsPerDay = sessionFinalKills / daysElapsed;
            const finalDeathsPerDay = sessionFinalDeaths / daysElapsed;

            if (currentFinalDeaths === 0 && sessionFinalDeaths === 0) {
                // Currently have "infinite" FKDR -> FKDR is computed as just finalKills
                const finalKillsProgression = computeStatProgression(
                    trackingHistory,
                    currentStats,
                    referenceDate,
                    "finalKills",
                    gamemode,
                );
                return {
                    ...finalKillsProgression,
                    stat,
                    finalKillsPerDay: finalKillsPerDay,
                    finalDeathsPerDay: finalDeathsPerDay, // 0
                    sessionFKDR,
                };
            }

            if (sessionFKDR === currentFKDR) {
                // Will make no progress
                // TODO: Display upward milestone and infinite time
                return {
                    error: true,
                    reason: "No progress",
                };
            }

            const nextMilestoneValue =
                sessionFKDR >= currentFKDR
                    ? Math.floor(currentFKDR) + 1
                    : Math.ceil(currentFKDR) - 1;

            // Variables:
            // k0 = currentFinalKills
            // k  = finalKillsPerDay
            // d0 = currentFinalDeaths
            // d  = finalDeathsPerDay
            // t  = daysToNextMilestone
            // M  = nextMilestoneValue
            //
            // Solve for t:
            // (k0 + kt) / (d0 + dt) = M
            // k0 + kt = Md0 + Mdt         ((d0 + dt > 0) d0 + d > 0 validated above, t chosen to be non-negative by choosing M appropriately)
            // (k - Md) t = Md0 - k0
            // t = (Md0 - k0) / (k - Md)

            if (nextMilestoneValue === currentFKDR) {
                // (k - Md) = 0
                // k = Md
                // M = k / d (= sessionFKDR)
                // Will approach but never reach milestone
                // TODO: Display upward milestone and infinite time
                return {
                    error: true,
                    reason: "No progress",
                };
            }

            // t = (Md0 - k0) / (k - Md)
            const daysUntilMilestone =
                (nextMilestoneValue * currentFinalDeaths - currentFinalKills) /
                (finalKillsPerDay - nextMilestoneValue * finalDeathsPerDay);

            if (!Number.isFinite(daysUntilMilestone)) {
                // Infinite time to reach milestone
                // TODO: Display milestone and infinite time
                return {
                    error: true,
                    reason: "Infinite time",
                };
            }

            const projectedMilestoneDate = new Date(
                referenceDate.getTime() +
                    daysUntilMilestone * 24 * 60 * 60 * 1000,
            );
            return {
                stat,
                trackingDataTimeInterval: { start: startDate, end: endDate },
                currentValue: currentFKDR,
                nextMilestoneValue,
                projectedMilestoneDate,
                referenceDate,
                // TODO: Fix progress per day (changes over time)
                progressPerDay:
                    (nextMilestoneValue - currentFKDR) / daysUntilMilestone,
                sessionFKDR,
                finalKillsPerDay,
                finalDeathsPerDay,
            };
        }
        case "kdr":
        case "index":
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

            const daysToNextMilestone =
                (nextMilestoneValue - currentValue) / increasePerDay;
            const projectedMilestoneDate = new Date(
                referenceDate.getTime() +
                    daysToNextMilestone * 24 * 60 * 60 * 1000,
            );

            return {
                stat,
                trackingDataTimeInterval: { start: startDate, end: endDate },
                currentValue,
                nextMilestoneValue,
                projectedMilestoneDate,
                referenceDate,
                progressPerDay: increasePerDay,
            };
        }

        case "winstreak":
            return { error: true, reason: "Not implemented" };
        default:
            stat satisfies never;
    }

    return { error: true, reason: "Unknown stat" };
};
