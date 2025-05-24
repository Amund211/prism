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

type APIHistory = readonly APIPlayerDataPIT[];

export type History = readonly PlayerDataPIT[];

interface HistoryQueryOptions {
    uuid: string;
    start: Date;
    end: Date;
    limit: number;
}
export const getHistoryQueryOptions = ({
    uuid,
    start,
    end,
    limit,
}: HistoryQueryOptions) => {
    const currentTime = new Date().getTime();
    const currentTimeIsInWindow =
        currentTime >= start.getTime() && currentTime <= end.getTime();

    const startISOString = start.toISOString();
    const endISOString = end.toISOString();

    return queryOptions({
        staleTime: currentTimeIsInWindow ? 1000 * 60 * 1 : Infinity,
        queryKey: ["history", uuid, startISOString, endISOString, limit],
        queryFn: async (): Promise<History> => {
            if (!isNormalizedUUID(uuid)) {
                captureMessage(
                    "Failed to get history: uuid is not normalized",
                    {
                        level: "error",
                        extra: {
                            uuid,
                            start: startISOString,
                            end: endISOString,
                            limit,
                        },
                    },
                );
                throw new Error(`UUID not normalized: ${uuid}`);
            }

            if (start.getTime() > end.getTime()) {
                return [];
            }
            const response = await fetch(
                `${env.VITE_FLASHLIGHT_URL}/v1/history`,
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
                        limit,
                    }),
                },
            ).catch((error: unknown) => {
                captureException(error, {
                    extra: {
                        uuid,
                        start: startISOString,
                        end: endISOString,
                        limit,
                        message: "Failed to get history: failed to fetch",
                    },
                });
                throw error;
            });

            if (!response.ok) {
                const text = await response.text().catch((error: unknown) => {
                    captureException(error, {
                        extra: {
                            message:
                                "Failed to get history: failed to read response text while handling response error",
                            uuid,
                            start: startISOString,
                            end: endISOString,
                            limit,
                        },
                    });
                    throw error;
                });

                captureMessage("Failed to get history: response error", {
                    level: "error",
                    extra: {
                        status: response.status,
                        statusText: response.statusText,
                        text,
                        uuid,
                        start: startISOString,
                        end: endISOString,
                        limit,
                    },
                });
                throw new Error(
                    `Failed to fetch history data from API. ${response.status.toString()} - ${response.statusText}: ${await response.text()}`,
                );
            }

            const apiHistory = (await response
                .json()
                .catch((error: unknown) => {
                    response
                        .text()
                        .then((text) => {
                            captureException(error, {
                                extra: {
                                    message:
                                        "Failed to get history: failed to parse json",
                                    uuid,
                                    start: startISOString,
                                    end: endISOString,
                                    limit,
                                    text,
                                },
                            });
                        })
                        .catch((textError: unknown) => {
                            captureException(textError, {
                                extra: {
                                    message:
                                        "Failed to get history: failed to get response text while handling json parse error",
                                    uuid,
                                    start: startISOString,
                                    end: endISOString,
                                    limit,
                                    jsonParseError: error,
                                },
                            });
                        });
                    throw error;
                })) as APIHistory;

            return apiHistory.map(apiToPlayerDataPIT);
        },
    });
};
