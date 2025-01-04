import { queryOptions } from "@tanstack/react-query";
import { env } from "@/env";

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

interface PlayerDataPIT {
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

type History = PlayerDataPIT[];

// const uuid = "a937646b-f115-44c3-8dbf-9ae4a65669a0";
const uuid = "ac04f297-f74c-44de-a24e-0083936ac59a";
const start = "2024-11-01T00:00:00Z";
const end = "2025-01-01T00:00:00Z";
const limit = 100;

export const historyQueryOptions = queryOptions({
    staleTime: 1000 * 60 * 60,
    queryKey: ["history", uuid, start, end, limit],
    queryFn: async (): Promise<History> => {
        const response = await fetch(`${env.VITE_FLASHLIGHT_URL}/v1/history`, {
            headers: {
                "Content-Type": "application/json",
            },
            method: "POST",
            body: JSON.stringify({ uuid, start, end, limit }),
        });
        const apiHistory = (await response.json()) as APIHistory;

        return apiHistory.map((apiPlayerData) => ({
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
