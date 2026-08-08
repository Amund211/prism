import { captureMessage } from "@sentry/react";
import { queryOptions } from "@tanstack/react-query";

import { flashlightFetch } from "#helpers/flashlight/fetch.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";
import { MS_PER_MINUTE } from "#time.ts";

import { apiToPlayerDataPIT } from "./playerdata.ts";
import type { APIPlayerDataPIT, PlayerDataPIT } from "./playerdata.ts";

export interface APISession {
    readonly start: APIPlayerDataPIT;
    readonly end: APIPlayerDataPIT;
    readonly consecutive: boolean;
    readonly ongoing: boolean;
}

type APISessions = readonly APISession[];

export interface Session {
    readonly start: PlayerDataPIT;
    readonly end: PlayerDataPIT;
    readonly extrapolated: boolean;
    readonly consecutive: boolean;
    readonly ongoing: boolean;
}
export type Sessions = readonly Session[];

export const apiToSession = (
    apiSession: APISession,
    extrapolated = false,
): Session => ({
    start: apiToPlayerDataPIT(apiSession.start),
    end: apiToPlayerDataPIT(apiSession.end),
    consecutive: apiSession.consecutive,
    ongoing: apiSession.ongoing,
    extrapolated,
});

interface SessionsQueryOptions {
    readonly uuid: string;
    readonly start: Date;
    readonly end: Date;
}
export const getSessionsQueryOptions = ({ uuid, start, end }: SessionsQueryOptions) => {
    const currentTime = Date.now();
    const currentTimeIsInWindow =
        currentTime >= start.getTime() && currentTime <= end.getTime();

    const startISOString = start.toISOString();
    const endISOString = end.toISOString();

    return queryOptions({
        staleTime: currentTimeIsInWindow ? MS_PER_MINUTE : Infinity,
        queryKey: ["sessions", uuid, startISOString, endISOString],
        queryFn: async (): Promise<Sessions> => {
            if (!isNormalizedUUID(uuid)) {
                captureMessage("Failed to get sessions: uuid is not normalized", {
                    level: "error",
                    extra: {
                        uuid,
                        start: startISOString,
                        end: endISOString,
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

            const apiSessions = await flashlightFetch<APISessions>("/v1/sessions", {
                init: {
                    method: "POST",
                    body: JSON.stringify({
                        uuid,
                        start: startISOString,
                        end: endISOString,
                    }),
                },
                errorContext: "Failed to get sessions",
                extra: {
                    uuid,
                    start: startISOString,
                    end: endISOString,
                },
            });

            return apiSessions.map((apiSession) => apiToSession(apiSession, false));
        },
    });
};
