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

export interface APIPlayerDataPIT {
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

export interface StatsPIT {
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

export const apiToPlayerDataPIT = (
    apiPlayerData: APIPlayerDataPIT,
): PlayerDataPIT => ({
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
});
