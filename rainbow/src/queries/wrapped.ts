import { captureException, captureMessage } from "@sentry/react";
import { queryOptions } from "@tanstack/react-query";

import { env } from "#env.ts";
import { getOrSetUserId } from "#helpers/userId.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";

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
    };
    readonly finalKillStreaks: {
        readonly overall: StreakInfo;
        readonly solo: StreakInfo;
        readonly doubles: StreakInfo;
        readonly threes: StreakInfo;
        readonly fours: StreakInfo;
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
    };
    readonly finalKillStreaks: {
        readonly overall: StreakInfo;
        readonly solo: StreakInfo;
        readonly doubles: StreakInfo;
        readonly threes: StreakInfo;
        readonly fours: StreakInfo;
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
interface APIWrappedData {
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
        staleTime: currentTimeIsInWindow ? 1000 * 60 * 5 : Infinity,
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

            const url = new URL(
                // NOTE: The flashlight API does **not** allow third-party access.
                //       Do not send any requests to any endpoints without explicit permission.
                //       Reach out on Discord for more information. https://discord.gg/k4FGUnEHYg
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

            const apiData = (await response.json().catch(async (error: unknown) => {
                try {
                    const text = await response.text();
                    captureException(error, {
                        extra: {
                            message: "Failed to get wrapped: failed to parse json",
                            uuid,
                            year,
                            timezone,
                            text,
                        },
                    });
                } catch (textError: unknown) {
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
                }
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
