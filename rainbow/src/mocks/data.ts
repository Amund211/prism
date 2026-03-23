import { isNormalizedUUID } from "#helpers/uuid.ts";
import type { APIPlayerDataPIT } from "#queries/playerdata.ts";
import type { APISession } from "#queries/sessions.ts";

interface User {
    username: string;
    uuid: string;
}

export const USERS = {
    player1: {
        username: "PlayerOne",
        uuid: "01234567-89ab-cdef-0123-456789abcdef",
    },
    player2: {
        username: "PlayerTwo",
        uuid: "abcdef01-2345-6789-abcd-ef0123456789",
    },
    player3: {
        username: "PlayerThree",
        uuid: "11111111-1111-1111-1111-111111111111",
    },
    player4: {
        username: "PlayerFour",
        uuid: "22222222-2222-2222-2222-222222222222",
    },
    player5: {
        username: "PlayerFive",
        uuid: "33333333-3333-3333-3333-333333333333",
    },
    player6: {
        username: "PlayerSix",
        uuid: "44444444-4444-4444-4444-444444444444",
    },
} as const satisfies Record<string, User>;

const seenUUIDs = new Set<string>();
const seenUsernames = new Set<string>();
for (const { uuid, username } of Object.values(USERS)) {
    if (!isNormalizedUUID(uuid)) {
        throw new Error(`Invalid UUID for user ${uuid}`);
    }
    if (seenUUIDs.has(uuid)) {
        throw new Error(`Duplicate UUID found: ${uuid}`);
    }
    seenUUIDs.add(uuid);

    if (seenUsernames.has(username)) {
        throw new Error(`Duplicate username found: ${username}`);
    }
    seenUsernames.add(username);
}

export const findUserByUUID = (uuid: string): User | null => {
    for (const user of Object.values(USERS)) {
        if (user.uuid === uuid) {
            return user;
        }
    }
    return null;
};

export const findUserByUsername = (username: string): User | null => {
    for (const user of Object.values(USERS)) {
        if (user.username.toLowerCase() === username.toLowerCase()) {
            return user;
        }
    }
    return null;
};

const makeStatsPIT = (multiplier: number) => ({
    winstreak: 3 * multiplier,
    gamesPlayed: 100 * multiplier,
    wins: 60 * multiplier,
    losses: 40 * multiplier,
    bedsBroken: 80 * multiplier,
    bedsLost: 30 * multiplier,
    finalKills: 150 * multiplier,
    finalDeaths: 50 * multiplier,
    kills: 200 * multiplier,
    deaths: 100 * multiplier,
});

export const makePlayerDataPIT = (
    uuid: string,
    queriedAt: string,
    multiplier = 1,
): APIPlayerDataPIT => ({
    uuid,
    queriedAt,
    experience: 500000 * multiplier,
    solo: makeStatsPIT(multiplier),
    doubles: makeStatsPIT(multiplier),
    threes: makeStatsPIT(multiplier),
    fours: makeStatsPIT(multiplier),
    overall: makeStatsPIT(multiplier * 4),
});

export const makeSession = (
    uuid: string,
    startTime: string,
    endTime: string,
): APISession => ({
    start: makePlayerDataPIT(uuid, startTime, 1),
    end: makePlayerDataPIT(uuid, endTime, 2),
    consecutive: true,
});

export const makeWrappedResponse = (uuid: string, year: number) => {
    const startTime = `${year.toString()}-01-01T00:00:00.000Z`;
    const endTime = `${year.toString()}-12-31T23:59:59.999Z`;
    const session = makeSession(uuid, startTime, endTime);

    return {
        success: true,
        uuid,
        year,
        totalSessions: 42,
        nonConsecutiveSessions: 5,
        yearStats: {
            start: makePlayerDataPIT(uuid, startTime, 1),
            end: makePlayerDataPIT(uuid, endTime, 3),
        },
        sessionStats: {
            sessionLengths: {
                totalHours: 210,
                longestHours: 8,
                shortestHours: 0.5,
                averageHours: 5,
            },
            sessionsPerMonth: {
                "1": 4,
                "2": 3,
                "3": 5,
                "4": 3,
                "5": 4,
                "6": 3,
                "7": 4,
                "8": 3,
                "9": 4,
                "10": 3,
                "11": 3,
                "12": 3,
            },
            bestSessions: {
                highestFKDR: session,
                mostKills: session,
                mostFinalKills: session,
                mostWins: session,
                longestSession: session,
            },
            averages: {
                sessionLengthHours: 5,
                gamesPlayed: 10,
                wins: 6,
                finalKills: 15,
            },
            winstreaks: {
                overall: { highest: 12, when: startTime },
                solo: { highest: 5, when: startTime },
                doubles: { highest: 8, when: startTime },
                threes: { highest: 6, when: startTime },
                fours: { highest: 10, when: startTime },
            },
            finalKillStreaks: {
                overall: { highest: 20, when: startTime },
                solo: { highest: 8, when: startTime },
                doubles: { highest: 12, when: startTime },
                threes: { highest: 10, when: startTime },
                fours: { highest: 15, when: startTime },
            },
            sessionCoverage: {
                gamesPlayedPercentage: 0.85,
                adjustedTotalHours: 180,
            },
            flawlessSessions: {
                count: 5,
                percentage: 0.12,
            },
            playtimeDistribution: {
                hourlyDistribution: Array.from({ length: 24 }, () => 1),
                dayHourDistribution: {
                    Monday: Array.from({ length: 24 }, () => 0.5),
                    Tuesday: Array.from({ length: 24 }, () => 0.5),
                    Wednesday: Array.from({ length: 24 }, () => 0.5),
                    Thursday: Array.from({ length: 24 }, () => 0.5),
                    Friday: Array.from({ length: 24 }, () => 1),
                    Saturday: Array.from({ length: 24 }, () => 1.5),
                    Sunday: Array.from({ length: 24 }, () => 1),
                },
            },
        },
    };
};
