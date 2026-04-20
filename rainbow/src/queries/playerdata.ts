interface APIStatsPIT {
    readonly winstreak: number | null;
    readonly gamesPlayed: number;
    readonly wins: number;
    readonly losses: number;
    readonly bedsBroken: number;
    readonly bedsLost: number;
    readonly finalKills: number;
    readonly finalDeaths: number;
    readonly kills: number;
    readonly deaths: number;
}

export interface APIPlayerDataPIT {
    readonly uuid: string;
    readonly queriedAt: string;
    readonly experience: number;
    readonly solo: APIStatsPIT;
    readonly doubles: APIStatsPIT;
    readonly threes: APIStatsPIT;
    readonly fours: APIStatsPIT;
    readonly overall: APIStatsPIT;
}

export interface StatsPIT {
    readonly winstreak: number | null;
    readonly gamesPlayed: number;
    readonly wins: number;
    readonly losses: number;
    readonly bedsBroken: number;
    readonly bedsLost: number;
    readonly finalKills: number;
    readonly finalDeaths: number;
    readonly kills: number;
    readonly deaths: number;
}

export interface PlayerDataPIT {
    readonly uuid: string;
    readonly queriedAt: Date;
    readonly experience: number;
    readonly solo: StatsPIT;
    readonly doubles: StatsPIT;
    readonly threes: StatsPIT;
    readonly fours: StatsPIT;
    readonly overall: StatsPIT;
}

export const apiToPlayerDataPIT = (apiPlayerData: APIPlayerDataPIT): PlayerDataPIT => ({
    uuid: apiPlayerData.uuid,
    queriedAt: new Date(apiPlayerData.queriedAt),
    experience: apiPlayerData.experience,
    solo: apiPlayerData.solo,
    doubles: apiPlayerData.doubles,
    threes: apiPlayerData.threes,
    fours: apiPlayerData.fours,
    overall: apiPlayerData.overall,
});
