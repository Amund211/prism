interface APIStatsPIT {
    winstreak: number | null;
    gamesPlayed: number;
    wins: number;
    losses: number;
    bedsBroken: number;
    bedsLost: number;
    finalKills: number;
    finalDeaths: number;
    kills: number;
    deaths: number;
}

export interface APIPlayerDataPIT {
    uuid: string;
    queriedAt: string;
    experience: number;
    solo: APIStatsPIT;
    doubles: APIStatsPIT;
    threes: APIStatsPIT;
    fours: APIStatsPIT;
    overall: APIStatsPIT;
}

export interface StatsPIT {
    winstreak: number | null;
    gamesPlayed: number;
    wins: number;
    losses: number;
    bedsBroken: number;
    bedsLost: number;
    finalKills: number;
    finalDeaths: number;
    kills: number;
    deaths: number;
}

export interface PlayerDataPIT {
    uuid: string;
    queriedAt: Date;
    experience: number;
    solo: StatsPIT;
    doubles: StatsPIT;
    threes: StatsPIT;
    fours: StatsPIT;
    overall: StatsPIT;
}

export const apiToPlayerDataPIT = (
    apiPlayerData: APIPlayerDataPIT,
): PlayerDataPIT => ({
    uuid: apiPlayerData.uuid,
    queriedAt: new Date(apiPlayerData.queriedAt),
    experience: apiPlayerData.experience,
    solo: apiPlayerData.solo,
    doubles: apiPlayerData.doubles,
    threes: apiPlayerData.threes,
    fours: apiPlayerData.fours,
    overall: apiPlayerData.overall,
});
