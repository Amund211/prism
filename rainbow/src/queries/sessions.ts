import { queryOptions } from "@tanstack/react-query";
import { env } from "#env.ts";
import {
    apiToPlayerDataPIT,
    type APIPlayerDataPIT,
    type PlayerDataPIT,
} from "./playerdata.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";
import { captureException, captureMessage } from "@sentry/react";
import { getOrSetUserId } from "#helpers/userId.ts";

interface APISession {
    start: APIPlayerDataPIT;
    end: APIPlayerDataPIT;
    consecutive: boolean;
}

type APISessions = readonly APISession[];

export interface Session {
    start: PlayerDataPIT;
    end: PlayerDataPIT;
    extrapolated: boolean;
    consecutive: boolean;
}
export type Sessions = readonly Session[];

interface SessionsQueryOptions {
    uuid: string;
    start: Date;
    end: Date;
}
export const getSessionsQueryOptions = ({
    uuid,
    start,
    end,
}: SessionsQueryOptions) => {
    const currentTime = new Date().getTime();
    const currentTimeIsInWindow =
        currentTime >= start.getTime() && currentTime <= end.getTime();

    const startISOString = start.toISOString();
    const endISOString = end.toISOString();

    return queryOptions({
        staleTime: currentTimeIsInWindow ? 1000 * 60 * 1 : Infinity,
        queryKey: ["sessions", uuid, startISOString, endISOString],
        queryFn: async (): Promise<Sessions> => {
            if (!isNormalizedUUID(uuid)) {
                captureMessage(
                    "Failed to get sessions: uuid is not normalized",
                    {
                        level: "error",
                        extra: {
                            uuid,
                            start: startISOString,
                            end: endISOString,
                        },
                    },
                );
                throw new Error(`UUID not normalized: ${uuid}`);
            }

            if (start.getTime() > end.getTime()) {
                return [];
            }
            const response = await fetch(
                `${env.VITE_FLASHLIGHT_URL}/v1/sessions`,
                {
                    headers: {
                        "Content-Type": "application/json",
                        "X-User-Id": getOrSetUserId(),
                    },
                    method: "POST",
                    body: JSON.stringify({
                        uuid,
                        start: startISOString,
                        end: endISOString,
                    }),
                },
            ).catch((error: unknown) => {
                captureException(error, {
                    extra: {
                        uuid,
                        start: startISOString,
                        end: endISOString,
                        message: "Failed to get sessions: failed to fetch",
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
                                "Failed to get sessions: failed to read response text when handling response error",
                            uuid,
                            start: startISOString,
                            end: endISOString,
                        },
                    });
                    throw error;
                });
                captureMessage("Failed to get sessions: response error", {
                    level: "error",
                    tags: {
                        status: response.status,
                        statusText: response.statusText,
                    },
                    extra: {
                        uuid,
                        start: startISOString,
                        end: endISOString,
                        text,
                    },
                });
                throw new Error(
                    `Failed to fetch session data from API. ${response.status.toString()} - ${response.statusText}: ${await response.text()}`,
                );
            }

            const apiSessions = (await response
                .json()
                .catch((error: unknown) => {
                    response
                        .text()
                        .then((text) => {
                            captureException(error, {
                                extra: {
                                    message:
                                        "Failed to get sessions: failed to parse json",
                                    uuid,
                                    start: startISOString,
                                    end: endISOString,
                                    text,
                                },
                            });
                        })
                        .catch((textError: unknown) => {
                            captureException(textError, {
                                extra: {
                                    message:
                                        "Failed to get sessions: failed to read response text when handling response error",
                                    uuid,
                                    start: startISOString,
                                    end: endISOString,
                                    jsonParseError: error,
                                },
                            });
                        });
                    throw error;
                })) as APISessions;

            return apiSessions.map((apiSession) => {
                return {
                    start: apiToPlayerDataPIT(apiSession.start),
                    end: apiToPlayerDataPIT(apiSession.end),
                    consecutive: apiSession.consecutive,
                    extrapolated: false,
                };
            });
        },
    });
};
