import { queryOptions } from "@tanstack/react-query";
import { env } from "#env.ts";

interface APIStatsPIT {
    winstreak: number | null;
    gamesPlayed: number | null;
    wins: number | null;
    losses: number | null;
    bedsBroken: number | null;
    bedsLost: number | null;
    finalKills: number | null;
    finalDeaths: number | null;
    kills: number | null;
    deaths: number | null;
}

interface APIPlayerDataPIT {
    id: string;
    dataFormatVersion: number;
    uuid: string;
    queriedAt: string;
    experience: number | null;
    solo: APIStatsPIT;
    doubles: APIStatsPIT;
    threes: APIStatsPIT;
    fours: APIStatsPIT;
    overall: APIStatsPIT;
}

type APIHistory = APIPlayerDataPIT[];

interface StatsPIT {
    winstreak: number | null;
    gamesPlayed: number | null;
    wins: number | null;
    losses: number | null;
    bedsBroken: number | null;
    bedsLost: number | null;
    finalKills: number | null;
    finalDeaths: number | null;
    kills: number | null;
    deaths: number | null;
}

export interface PlayerDataPIT {
    id: string;
    dataFormatVersion: number;
    uuid: string;
    queriedAt: Date;
    experience: number | null;
    solo: StatsPIT;
    doubles: StatsPIT;
    threes: StatsPIT;
    fours: StatsPIT;
    overall: StatsPIT;
}

export type History = PlayerDataPIT[];

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
        staleTime: currentTimeIsInWindow ? 1000 * 60 : Infinity,
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
                .map((apiPlayerData) => ({
                    id: apiPlayerData.id,
                    dataFormatVersion: apiPlayerData.dataFormatVersion,
                    uuid: apiPlayerData.uuid,
                    queriedAt: new Date(apiPlayerData.queriedAt),
                    experience: apiPlayerData.experience,
                    solo: apiPlayerData.solo,
                    doubles: apiPlayerData.doubles,
                    threes: apiPlayerData.threes,
                    fours: apiPlayerData.fours,
                    overall: apiPlayerData.overall,
                }));
        },
    });
};
