import { queryOptions } from "@tanstack/react-query";
import { env } from "#env.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";
import { captureException, captureMessage } from "@sentry/react";
import { getOrSetUserId } from "#helpers/userId.ts";
import {
    apiToPlayerDataPIT,
    type APIPlayerDataPIT,
    type PlayerDataPIT,
} from "./playerdata.ts";
import { apiToSession, type APISession, type Session } from "./sessions.ts";

interface StreakInfo {
    highest: number;
    when: string;
}

interface PlaytimeDistribution {
    hourlyDistribution: number[]; // 24 elements for UTC hours 0-23
    dayHourDistribution: Record<string, number[]>; // Weekday name -> 24 elements for UTC hours
}

// API Session statistics - as returned from API before conversion
interface APISessionStats {
    sessionLengths: {
        totalHours: number;
        longestHours: number;
        shortestHours: number;
        averageHours: number;
    };
    sessionsPerMonth: Record<string, number>;
    bestSessions: {
        highestFKDR: APISession;
        mostKills: APISession;
        mostFinalKills: APISession;
        mostWins: APISession;
        longestSession: APISession;
        mostWinsPerHour?: APISession;
        mostFinalsPerHour?: APISession;
    };
    averages: {
        sessionLengthHours: number;
        gamesPlayed: number;
        wins: number;
        finalKills: number;
    };
    winstreaks: {
        overall: StreakInfo;
        solo: StreakInfo;
        doubles: StreakInfo;
        threes: StreakInfo;
        fours: StreakInfo;
    };
    finalKillStreaks: {
        overall: StreakInfo;
        solo: StreakInfo;
        doubles: StreakInfo;
        threes: StreakInfo;
        fours: StreakInfo;
    };
    sessionCoverage: {
        gamesPlayedPercentage: number;
        adjustedTotalHours: number;
    };
    flawlessSessions: {
        count: number;
        percentage: number;
    };
    playtimeDistribution: PlaytimeDistribution;
}

// Session statistics - only present when there is at least one consecutive session
interface SessionStats {
    sessionLengths: {
        totalHours: number;
        longestHours: number;
        shortestHours: number;
        averageHours: number;
    };
    sessionsPerMonth: Record<string, number>;
    bestSessions: {
        highestFKDR: Session;
        mostKills: Session;
        mostFinalKills: Session;
        mostWins: Session;
        longestSession: Session;
        mostWinsPerHour?: Session;
        mostFinalsPerHour?: Session;
    };
    averages: {
        sessionLengthHours: number;
        gamesPlayed: number;
        wins: number;
        finalKills: number;
    };
    winstreaks: {
        overall: StreakInfo;
        solo: StreakInfo;
        doubles: StreakInfo;
        threes: StreakInfo;
        fours: StreakInfo;
    };
    finalKillStreaks: {
        overall: StreakInfo;
        solo: StreakInfo;
        doubles: StreakInfo;
        threes: StreakInfo;
        fours: StreakInfo;
    };
    sessionCoverage: {
        gamesPlayedPercentage: number;
        adjustedTotalHours: number;
    };
    flawlessSessions: {
        count: number;
        percentage: number;
    };
    playtimeDistribution: PlaytimeDistribution;
}

// API response structure (before conversion)
interface APIWrappedData {
    success: boolean;
    uuid: string;
    year: number;
    totalSessions: number;
    nonConsecutiveSessions: number;
    yearStats?: {
        start: APIPlayerDataPIT;
        end: APIPlayerDataPIT;
    };
    sessionStats?: APISessionStats;
    cause?: string;
}

export interface WrappedData {
    success: boolean;
    uuid: string;
    year: number;
    totalSessions: number;
    nonConsecutiveSessions: number;
    yearStats?: {
        start: PlayerDataPIT;
        end: PlayerDataPIT;
    };
    // Session stats are nested and only present when there's at least one consecutive session
    sessionStats?: SessionStats;
    cause?: string;
}

interface WrappedQueryOptions {
    uuid: string;
    year: number;
    timezone: string; // IANA timezone (e.g., "Europe/Oslo", "America/New_York")
}

export const getWrappedQueryOptions = ({
    uuid,
    year,
    timezone,
}: WrappedQueryOptions) => {
    const currentYear = new Date().getFullYear();
    const currentTimeIsInWindow = currentYear === year;

    return queryOptions({
        staleTime: currentTimeIsInWindow ? 1000 * 60 * 5 : Infinity,
        queryKey: ["wrapped", uuid, year, timezone],
        queryFn: async (): Promise<WrappedData> => {
            if (!isNormalizedUUID(uuid)) {
                captureMessage(
                    "Failed to get wrapped: uuid is not normalized",
                    {
                        level: "error",
                        extra: {
                            uuid,
                            year,
                            timezone,
                        },
                    },
                );
                throw new Error(`UUID not normalized: ${uuid}`);
            }

            const url = new URL(
                `${env.VITE_FLASHLIGHT_URL}/v1/wrapped/${uuid}/${year.toString()}`,
            );
            url.searchParams.set("timezone", timezone);

            const response = await fetch(url, {
                headers: {
                    "Content-Type": "application/json",
                    "X-User-Id": getOrSetUserId(),
                },
                method: "GET",
            }).catch((error: unknown) => {
                captureException(error, {
                    extra: {
                        uuid,
                        year,
                        timezone,
                        message: "Failed to get wrapped: failed to fetch",
                    },
                });
                throw error;
            });

            if (!response.ok) {
                const text = await response.text().catch((error: unknown) => {
                    captureException(error, {
                        tags: {
                            status: response.status,
                            statusText: response.statusText,
                        },
                        extra: {
                            message:
                                "Failed to get wrapped: failed to read response text when handling response error",
                            uuid,
                            year,
                        },
                    });
                    throw error;
                });
                captureMessage("Failed to get wrapped: response error", {
                    level: "error",
                    tags: {
                        status: response.status,
                        statusText: response.statusText,
                    },
                    extra: {
                        uuid,
                        year,
                        text,
                    },
                });
                throw new Error(
                    `Failed to fetch wrapped data from API. ${response.status.toString()} - ${response.statusText}: ${text}`,
                );
            }

            const apiData = (await response.json().catch((error: unknown) => {
                response
                    .text()
                    .then((text) => {
                        captureException(error, {
                            extra: {
                                message:
                                    "Failed to get wrapped: failed to parse json",
                                uuid,
                                year,
                                timezone,
                                text,
                            },
                        });
                    })
                    .catch((textError: unknown) => {
                        captureException(textError, {
                            extra: {
                                message:
                                    "Failed to get wrapped: failed to read response text when handling response error",
                                uuid,
                                year,
                                timezone,
                                jsonParseError: error,
                            },
                        });
                    });
                throw error;
            })) as APIWrappedData;

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
                                  apiData.sessionStats.bestSessions
                                      .mostFinalKills,
                              ),
                              mostWins: apiToSession(
                                  apiData.sessionStats.bestSessions.mostWins,
                              ),
                              longestSession: apiToSession(
                                  apiData.sessionStats.bestSessions
                                      .longestSession,
                              ),
                              mostWinsPerHour: apiData.sessionStats.bestSessions
                                  .mostWinsPerHour
                                  ? apiToSession(
                                        apiData.sessionStats.bestSessions
                                            .mostWinsPerHour,
                                    )
                                  : undefined,
                              mostFinalsPerHour: apiData.sessionStats
                                  .bestSessions.mostFinalsPerHour
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
