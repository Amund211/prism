import { captureMessage } from "@sentry/react";
import { queryOptions } from "@tanstack/react-query";

import { flashlightFetch } from "#helpers/flashlight/fetch.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";
import { MS_PER_MINUTE } from "#time.ts";

import { apiToPlayerDataPIT } from "./playerdata.ts";
import type { APIPlayerDataPIT, PlayerDataPIT } from "./playerdata.ts";

type APIHistory = readonly APIPlayerDataPIT[];

export type History = readonly PlayerDataPIT[];

interface HistoryQueryOptions {
    readonly uuid: string;
    readonly start: Date;
    readonly end: Date;
    readonly limit: number;
}
export const getHistoryQueryOptions = ({
    uuid,
    start,
    end,
    limit,
}: HistoryQueryOptions) => {
    const currentTime = Date.now();
    const currentTimeIsInWindow =
        currentTime >= start.getTime() && currentTime <= end.getTime();

    const startISOString = start.toISOString();
    const endISOString = end.toISOString();

    return queryOptions({
        staleTime: currentTimeIsInWindow ? MS_PER_MINUTE : Infinity,
        queryKey: ["history", uuid, startISOString, endISOString, limit],
        queryFn: async (): Promise<History> => {
            if (!isNormalizedUUID(uuid)) {
                captureMessage("Failed to get history: uuid is not normalized", {
                    level: "error",
                    extra: {
                        uuid,
                        start: startISOString,
                        end: endISOString,
                        limit,
                    },
                });
                throw new Error(`UUID not normalized: ${uuid}`);
            }

            // NOTE: Work around exhaustive deps lint rule
            // oxlint-disable-next-line eslint/no-shadow
            const start = new Date(startISOString);
            // oxlint-disable-next-line eslint/no-shadow
            const end = new Date(endISOString);

            if (start.getTime() > end.getTime()) {
                return [];
            }

            const apiHistory = await flashlightFetch<APIHistory>("/v1/history", {
                init: {
                    method: "POST",
                    body: JSON.stringify({
                        uuid,
                        start: startISOString,
                        end: endISOString,
                        limit,
                    }),
                },
                errorContext: "Failed to get history",
                extra: {
                    uuid,
                    start: startISOString,
                    end: endISOString,
                    limit,
                },
            });

            return apiHistory.map(apiToPlayerDataPIT);
        },
    });
};
