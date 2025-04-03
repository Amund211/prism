import { queryOptions } from "@tanstack/react-query";
import { env } from "#env.ts";
import {
    apiToPlayerDataPIT,
    type APIPlayerDataPIT,
    type PlayerDataPIT,
} from "./playerdata.ts";

interface APISession {
    start: APIPlayerDataPIT;
    end: APIPlayerDataPIT;
}

type APISessions = readonly APISession[];

interface Session {
    start: PlayerDataPIT;
    end: PlayerDataPIT;
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
            if (start.getTime() > end.getTime()) {
                return [];
            }
            const response = await fetch(
                `${env.VITE_FLASHLIGHT_URL}/v1/sessions`,
                {
                    headers: {
                        "Content-Type": "application/json",
                    },
                    method: "POST",
                    body: JSON.stringify({
                        uuid,
                        start: startISOString,
                        end: endISOString,
                    }),
                },
            );

            if (!response.ok) {
                throw new Error(
                    `Failed to fetch session data from API. ${response.status.toString()} - ${response.statusText}: ${await response.text()}`,
                );
            }

            const apiSessions = (await response.json()) as APISessions;

            return apiSessions
                .filter(
                    ({ start, end }) =>
                        start.dataFormatVersion === 1 &&
                        end.dataFormatVersion === 1,
                )
                .map((apiSession) => {
                    return {
                        start: apiToPlayerDataPIT(apiSession.start),
                        end: apiToPlayerDataPIT(apiSession.end),
                    };
                });
        },
    });
};
