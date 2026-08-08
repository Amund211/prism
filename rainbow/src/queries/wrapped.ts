import { captureMessage } from "@sentry/react";
import { queryOptions } from "@tanstack/react-query";

import { flashlightFetch } from "#helpers/flashlight/fetch.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";
import { MS_PER_MINUTE } from "#time.ts";

import { apiToPlayerDataPIT } from "./playerdata.ts";
import type { APIPlayerDataPIT, PlayerDataPIT } from "./playerdata.ts";
import { apiToSession } from "./sessions.ts";
import type { APISession, Session } from "./sessions.ts";

interface StreakInfo {
    readonly highest: number;
    readonly when: string;
}

interface PlaytimeDistribution {
    readonly hourlyDistribution: readonly number[]; // 24 elements for UTC hours 0-23
    readonly dayHourDistribution: Readonly<Record<string, readonly number[]>>; // Weekday name -> 24 elements for UTC hours
}

// API Session statistics - as returned from API before conversion
interface APISessionStats {
    readonly sessionLengths: {
        readonly totalHours: number;
        readonly longestHours: number;
        readonly shortestHours: number;
        readonly averageHours: number;
    };
    readonly sessionsPerMonth: Readonly<Record<string, number>>;
    readonly bestSessions: {
        readonly highestFKDR: APISession;
        readonly mostKills: APISession;
        readonly mostFinalKills: APISession;
        readonly mostWins: APISession;
        readonly longestSession: APISession;
        readonly mostWinsPerHour?: APISession;
        readonly mostFinalsPerHour?: APISession;
    };
    readonly averages: {
        readonly sessionLengthHours: number;
        readonly gamesPlayed: number;
        readonly wins: number;
        readonly finalKills: number;
    };
    readonly winstreaks: {
        readonly overall: StreakInfo;
        readonly solo: StreakInfo;
        readonly doubles: StreakInfo;
        readonly threes: StreakInfo;
        readonly fours: StreakInfo;
        readonly "4v4": StreakInfo;
    };
    readonly finalKillStreaks: {
        readonly overall: StreakInfo;
        readonly solo: StreakInfo;
        readonly doubles: StreakInfo;
        readonly threes: StreakInfo;
        readonly fours: StreakInfo;
        readonly "4v4": StreakInfo;
    };
    readonly sessionCoverage: {
        readonly gamesPlayedPercentage: number;
        readonly adjustedTotalHours: number;
    };
    readonly flawlessSessions: {
        readonly count: number;
        readonly percentage: number;
    };
    readonly playtimeDistribution: PlaytimeDistribution;
}

// Session statistics - only present when there is at least one consecutive session
interface SessionStats {
    readonly sessionLengths: {
        readonly totalHours: number;
        readonly longestHours: number;
        readonly shortestHours: number;
        readonly averageHours: number;
    };
    readonly sessionsPerMonth: Readonly<Record<string, number>>;
    readonly bestSessions: {
        readonly highestFKDR: Session;
        readonly mostKills: Session;
        readonly mostFinalKills: Session;
        readonly mostWins: Session;
        readonly longestSession: Session;
        readonly mostWinsPerHour?: Session;
        readonly mostFinalsPerHour?: Session;
    };
    readonly averages: {
        readonly sessionLengthHours: number;
        readonly gamesPlayed: number;
        readonly wins: number;
        readonly finalKills: number;
    };
    readonly winstreaks: {
        readonly overall: StreakInfo;
        readonly solo: StreakInfo;
        readonly doubles: StreakInfo;
        readonly threes: StreakInfo;
        readonly fours: StreakInfo;
        readonly "4v4": StreakInfo;
    };
    readonly finalKillStreaks: {
        readonly overall: StreakInfo;
        readonly solo: StreakInfo;
        readonly doubles: StreakInfo;
        readonly threes: StreakInfo;
        readonly fours: StreakInfo;
        readonly "4v4": StreakInfo;
    };
    readonly sessionCoverage: {
        readonly gamesPlayedPercentage: number;
        readonly adjustedTotalHours: number;
    };
    readonly flawlessSessions: {
        readonly count: number;
        readonly percentage: number;
    };
    readonly playtimeDistribution: PlaytimeDistribution;
}

// API response structure (before conversion)
export interface APIWrappedData {
    readonly success: boolean;
    readonly uuid: string;
    readonly year: number;
    readonly totalSessions: number;
    readonly nonConsecutiveSessions: number;
    readonly yearStats?: {
        readonly start: APIPlayerDataPIT;
        readonly end: APIPlayerDataPIT;
    };
    readonly sessionStats?: APISessionStats;
    readonly cause?: string;
}

export interface WrappedData {
    readonly success: boolean;
    readonly uuid: string;
    readonly year: number;
    readonly totalSessions: number;
    readonly nonConsecutiveSessions: number;
    readonly yearStats?: {
        readonly start: PlayerDataPIT;
        readonly end: PlayerDataPIT;
    };
    // Session stats are nested and only present when there's at least one consecutive session
    readonly sessionStats?: SessionStats;
    readonly cause?: string;
}

interface WrappedQueryOptions {
    readonly uuid: string;
    readonly year: number;
    readonly timezone: string; // IANA timezone (e.g., "Europe/Oslo", "America/New_York")
}

export const getWrappedQueryOptions = ({
    uuid,
    year,
    timezone,
}: WrappedQueryOptions) => {
    const currentYear = new Date().getFullYear();
    const currentTimeIsInWindow = currentYear === year;

    return queryOptions({
        staleTime: currentTimeIsInWindow ? MS_PER_MINUTE * 5 : Infinity,
        queryKey: ["wrapped", uuid, year, timezone],
        queryFn: async (): Promise<WrappedData> => {
            if (!isNormalizedUUID(uuid)) {
                captureMessage("Failed to get wrapped: uuid is not normalized", {
                    level: "error",
                    extra: {
                        uuid,
                        year,
                        timezone,
                    },
                });
                throw new Error(`UUID not normalized: ${uuid}`);
            }

            const search = new URLSearchParams({ timezone });

            const apiData = await flashlightFetch<APIWrappedData>(
                `/v1/wrapped/${uuid}/${year.toString()}?${search.toString()}`,
                {
                    errorContext: "Failed to get wrapped",
                    extra: { uuid, year, timezone },
                },
            );

            // Convert the API response to application format, keeping nested structure
            const convertedData: WrappedData = {
                success: apiData.success,
                uuid: apiData.uuid,
                year: apiData.year,
                totalSessions: apiData.totalSessions,
                nonConsecutiveSessions: apiData.nonConsecutiveSessions,
                yearStats: apiData.yearStats
                    ? {
                          start: apiToPlayerDataPIT(apiData.yearStats.start),
                          end: apiToPlayerDataPIT(apiData.yearStats.end),
                      }
                    : undefined,
                // Convert sessionStats, including bestSessions
                sessionStats: apiData.sessionStats
                    ? {
                          ...apiData.sessionStats,
                          bestSessions: {
                              highestFKDR: apiToSession(
                                  apiData.sessionStats.bestSessions.highestFKDR,
                              ),
                              mostKills: apiToSession(
                                  apiData.sessionStats.bestSessions.mostKills,
                              ),
                              mostFinalKills: apiToSession(
                                  apiData.sessionStats.bestSessions.mostFinalKills,
                              ),
                              mostWins: apiToSession(
                                  apiData.sessionStats.bestSessions.mostWins,
                              ),
                              longestSession: apiToSession(
                                  apiData.sessionStats.bestSessions.longestSession,
                              ),
                              mostWinsPerHour: apiData.sessionStats.bestSessions
                                  .mostWinsPerHour
                                  ? apiToSession(
                                        apiData.sessionStats.bestSessions
                                            .mostWinsPerHour,
                                    )
                                  : undefined,
                              mostFinalsPerHour: apiData.sessionStats.bestSessions
                                  .mostFinalsPerHour
                                  ? apiToSession(
                                        apiData.sessionStats.bestSessions
                                            .mostFinalsPerHour,
                                    )
                                  : undefined,
                          },
                      }
                    : undefined,
                cause: apiData.cause,
            };

            return convertedData;
        },
    });
};
