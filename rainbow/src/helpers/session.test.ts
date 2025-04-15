import test from "node:test";
import assert from "node:assert";
import { addExtrapolatedSessions } from "./session.ts";
import type { PlayerDataPIT, StatsPIT } from "#queries/playerdata.ts";
import { randomUUID } from "node:crypto";

const playerUUID = randomUUID();

const makeStatsPIT = (gamesPlayed: number): StatsPIT => ({
    gamesPlayed,
    wins: 0,
    losses: 0,
    kills: 0,
    deaths: 0,
    finalKills: 0,
    finalDeaths: 0,
    winstreak: 0,
    bedsBroken: 0,
    bedsLost: 0,
});
const makePlayerDataPIT = (
    gamesPlayed: number,
    experience: number,
): PlayerDataPIT => ({
    id: `${playerUUID}-${gamesPlayed.toString()}-${experience.toString()}`,
    dataFormatVersion: gamesPlayed, // This shows up early in the test diff, so it makes it easier to debug
    uuid: playerUUID,
    queriedAt: new Date(1_700_000_000_000 + gamesPlayed * 60_000),
    experience,
    overall: makeStatsPIT(gamesPlayed),
    solo: makeStatsPIT(0),
    doubles: makeStatsPIT(0),
    threes: makeStatsPIT(0),
    fours: makeStatsPIT(gamesPlayed),
});

await test("addExtrapolatedSessions", async (t) => {
    const cases = [
        {
            name: "No sessions no history",
            input: [],
            history: undefined,
            expected: [],
        },
        {
            name: "Sessions undefined history",
            input: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(11, 12_000),
                    extrapolated: false,
                    consecutive: true,
                },
            ],
            history: undefined,
            expected: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(11, 12_000),
                    extrapolated: false,
                    consecutive: true,
                },
            ],
        },
        {
            name: "Sessions no history",
            input: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(13, 12_000),
                    extrapolated: false,
                    consecutive: false,
                },
            ],
            history: [],
            expected: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(13, 12_000),
                    extrapolated: false,
                    consecutive: false,
                },
            ],
        },
        {
            name: "Sessions one history (impossible)",
            input: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(11, 12_000),
                    extrapolated: false,
                    consecutive: true,
                },
            ],
            history: [makePlayerDataPIT(0, 0)],
            // This should not be possible -> just return the session
            expected: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(11, 12_000),
                    extrapolated: false,
                    consecutive: true,
                },
            ],
        },
        {
            name: "no sessions",
            input: [],
            history: [
                makePlayerDataPIT(10, 11_000),
                makePlayerDataPIT(12, 12_000),
            ],
            expected: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(12, 12_000),
                    extrapolated: true,
                    consecutive: false,
                },
            ],
        },
        {
            name: "Sessions match history",
            input: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(12, 12_000),
                    extrapolated: false,
                    consecutive: false,
                },
            ],
            history: [
                makePlayerDataPIT(10, 11_000),
                makePlayerDataPIT(12, 12_000),
            ],
            expected: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(12, 12_000),
                    extrapolated: false,
                    consecutive: false,
                },
            ],
        },
        {
            name: "extraplated session at start",
            input: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(11, 12_000),
                    extrapolated: false,
                    consecutive: true,
                },
            ],
            history: [
                makePlayerDataPIT(8, 9_000),
                makePlayerDataPIT(11, 12_000),
            ],
            expected: [
                {
                    start: makePlayerDataPIT(8, 9_000),
                    end: makePlayerDataPIT(10, 11_000),
                    extrapolated: true,
                    consecutive: false,
                },
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(11, 12_000),
                    extrapolated: false,
                    consecutive: true,
                },
            ],
        },
        {
            name: "extraplated session at end",
            input: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(11, 12_000),
                    extrapolated: false,
                    consecutive: true,
                },
            ],
            history: [
                makePlayerDataPIT(10, 11_000),
                makePlayerDataPIT(16, 21_000),
            ],
            expected: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(11, 12_000),
                    extrapolated: false,
                    consecutive: true,
                },
                {
                    start: makePlayerDataPIT(11, 12_000),
                    end: makePlayerDataPIT(16, 21_000),
                    extrapolated: true,
                    consecutive: false,
                },
            ],
        },
        {
            name: "extraplated session at start and end",
            input: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(11, 12_000),
                    extrapolated: false,
                    consecutive: true,
                },
            ],
            history: [
                makePlayerDataPIT(8, 9_000),
                makePlayerDataPIT(16, 21_000),
            ],
            expected: [
                {
                    start: makePlayerDataPIT(8, 9_000),
                    end: makePlayerDataPIT(10, 11_000),
                    extrapolated: true,
                    consecutive: false,
                },
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(11, 12_000),
                    extrapolated: false,
                    consecutive: true,
                },
                {
                    start: makePlayerDataPIT(11, 12_000),
                    end: makePlayerDataPIT(16, 21_000),
                    extrapolated: true,
                    consecutive: false,
                },
            ],
        },
        {
            name: "extraplated session at start and end and middle",
            input: [
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(11, 12_000),
                    extrapolated: false,
                    consecutive: true,
                },
                {
                    start: makePlayerDataPIT(12, 14_000),
                    end: makePlayerDataPIT(13, 16_000),
                    extrapolated: false,
                    consecutive: true,
                },
                {
                    start: makePlayerDataPIT(14, 17_000),
                    end: makePlayerDataPIT(15, 18_000),
                    extrapolated: false,
                    consecutive: true,
                },
            ],
            history: [
                makePlayerDataPIT(8, 9_000),
                makePlayerDataPIT(16, 21_000),
            ],
            expected: [
                {
                    start: makePlayerDataPIT(8, 9_000),
                    end: makePlayerDataPIT(10, 11_000),
                    extrapolated: true,
                    consecutive: false,
                },
                {
                    start: makePlayerDataPIT(10, 11_000),
                    end: makePlayerDataPIT(11, 12_000),
                    extrapolated: false,
                    consecutive: true,
                },
                {
                    start: makePlayerDataPIT(11, 12_000),
                    end: makePlayerDataPIT(12, 14_000),
                    extrapolated: true,
                    consecutive: true,
                },
                {
                    start: makePlayerDataPIT(12, 14_000),
                    end: makePlayerDataPIT(13, 16_000),
                    extrapolated: false,
                    consecutive: true,
                },
                {
                    start: makePlayerDataPIT(13, 16_000),
                    end: makePlayerDataPIT(14, 17_000),
                    extrapolated: true,
                    consecutive: true,
                },
                {
                    start: makePlayerDataPIT(14, 17_000),
                    end: makePlayerDataPIT(15, 18_000),
                    extrapolated: false,
                    consecutive: true,
                },
                {
                    start: makePlayerDataPIT(15, 18_000),
                    end: makePlayerDataPIT(16, 21_000),
                    extrapolated: true,
                    consecutive: true,
                },
            ],
        },
    ];

    for (const tc of cases) {
        await t.test(tc.name, () => {
            const result = addExtrapolatedSessions(tc.input, tc.history);
            assert.deepStrictEqual(result, tc.expected);
        });
    }
});
