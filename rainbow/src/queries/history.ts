import { queryOptions } from "@tanstack/react-query";
import { env } from "#env.ts";
import {
    apiToPlayerDataPIT,
    type APIPlayerDataPIT,
    type PlayerDataPIT,
} from "./playerdata.ts";

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
        staleTime: currentTimeIsInWindow ? 1000 * 60 * 5 : Infinity,
        queryKey: ["history", uuid, startISOString, endISOString, limit],
        queryFn: async (): Promise<History> => {
            if (start.getTime() > end.getTime()) {
                return [];
            }
            const response = await fetch(
                `${env.VITE_FLASHLIGHT_URL}/v1/history`,
                {
                    headers: {
                        "Content-Type": "application/json",
                    },
                    method: "POST",
                    body: JSON.stringify({
                        uuid,
                        start: startISOString,
                        end: endISOString,
                        limit,
                    }),
                },
            );
            const apiHistory = (await response.json()) as APIHistory;

            return apiHistory
                .filter(({ dataFormatVersion }) => dataFormatVersion === 1)
                .map(apiToPlayerDataPIT);
        },
    });
};
